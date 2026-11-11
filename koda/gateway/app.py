"""FastAPI REST + WebSocket hub and context-preserving Koda orchestrator."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from koda.config import KodaSettings
from koda.daemon.scheduler import MorningBriefingBuilder, ProactiveDaemon
from koda.daemon.telegram_bridge import TelegramBridge
from koda.memory.extractor import extract_candidate_facts, update_rolling_summary
from koda.memory.store import MemoryStore
from koda.opencode.client import OpenCodeClient, OpenCodeError
from koda.opencode.models import Lane
from koda.opencode.supervisor import OpenCodeSupervisor
from koda.router.engine import AllFreeModelsExhaustedError, FreeModelRouter, RouterShiftEvent
from koda.router.state import RouterTelemetryStore
from koda.safety.gate import SafetyGate
from koda.tools.bundle import build_default_tool_registry, execute_tool_with_registry
from koda.tools.registry import ToolRegistry
from koda.voice.pipeline import VoicePipeline

_TOOL_TAG_RE = re.compile(r"<koda_tool>\s*(\{.*?\})\s*</koda_tool>", re.DOTALL)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    conversation_id: str = "default"
    lane: Lane | None = None
    preferred_model_id: str | None = None
    files: list[str] | None = None
    has_image: bool = False
    has_audio_or_video: bool = False


class FactCreateRequest(BaseModel):
    category: str = "preference"
    key: str
    value: str


class ApprovalResolveRequest(BaseModel):
    approved: bool


class ModelToggleRequest(BaseModel):
    disabled: bool


class RoutineCreateRequest(BaseModel):
    name: str
    trigger_phrase: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    cron_expr: str = ""
    enabled: bool = True


class ToolRunRequest(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1)


class VoiceToggleRequest(BaseModel):
    enabled: bool


class TimerCreateRequest(BaseModel):
    label: str = Field(min_length=1)
    delay_sec: float = Field(ge=0.0, le=86400.0)


class ConnectionManager:
    """Manages active WebSocket HUD & Dynamic Island subscribers."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {"type": event_type, "payload": payload, "ts": time.time()}
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


ToolCallback = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class KodaService:
    """Core runtime wiring together OpenCode, FreeModelRouter, MemoryStore, SafetyGate, and Tools."""

    def __init__(
        self,
        *,
        settings: KodaSettings | None = None,
        client: OpenCodeClient | None = None,
        managed_opencode: bool = True,
        tool_executor: ToolCallback | None = None,
        tool_catalog_prompt: str = "",
    ) -> None:
        self.settings = settings or KodaSettings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory = MemoryStore(db_path=self.settings.db_path)
        self.telemetry = RouterTelemetryStore(db_path=self.settings.db_path)
        self.ws_manager = ConnectionManager()
        self._pending_events: list[tuple[str, dict[str, Any]]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self.koda_state: str = "idle"
        self.tool_executor = tool_executor
        self.tool_catalog_prompt = tool_catalog_prompt
        self._barge_in_hook: Callable[[], Any] | None = None

        self.managed_opencode = managed_opencode
        self.supervisor: OpenCodeSupervisor | None = None
        if managed_opencode and client is None:
            self.supervisor = OpenCodeSupervisor(
                exe_path=self.settings.opencode_exe,
                host=self.settings.opencode_serve_host,
                port=self.settings.opencode_serve_port,
                username=self.settings.opencode_server_username,
                password=self.settings.opencode_server_password.get_secret_value(),
                log_path=self.settings.data_dir / "opencode_serve.log",
            )

        self.client: OpenCodeClient = client or OpenCodeClient(
            base_url=self.settings.opencode_serve_url,
            username=self.settings.opencode_server_username,
            password=self.settings.opencode_server_password.get_secret_value(),
            timeout_sec=self.settings.opencode_timeout_sec,
        )

        self.safety = SafetyGate(
            allowed_roots=self.settings.parsed_allowed_roots,
            memory=self.memory,
            on_approval_requested=lambda rec: self._queue_ws_event("approval_required", rec.model_dump()),
        )
        self.tool_registry: ToolRegistry = build_default_tool_registry(
            settings=self.settings,
            memory=self.memory,
            safety_gate=self.safety,
        )
        if self.tool_executor is None:
            self.tool_executor = execute_tool_with_registry(self.tool_registry)
        if not self.tool_catalog_prompt:
            self.tool_catalog_prompt = self.tool_registry.catalog_prompt()
        self.voice = VoicePipeline(
            wake_word=self.settings.wake_word,
            stt_model=self.settings.stt_model,
            tts_voice=self.settings.tts_voice,
            on_transcript=self._handle_voice_transcript,
            on_state_change=lambda st: self._queue_ws_event("koda_state", {"state": st, "detail": "voice"}),
        )
        self._barge_in_hook = self.voice.barge_in
        self.daemon = ProactiveDaemon(
            memory=self.memory,
            recall_enabled=False,
            on_notification=lambda msg: self._queue_ws_event("notification", {"message": msg}),
        )
        self.telegram = TelegramBridge(
            bot_token=self.settings.telegram_bot_token.get_secret_value(),
            allowed_user_id=self.settings.telegram_allowed_user_id,
            on_prompt=self._handle_voice_transcript,
            on_approve=self._resolve_approval_async,
        )
        self.router = FreeModelRouter(
            client=self.client,
            telemetry=self.telemetry,
            allow_google_free=self.settings.allow_google_free,
            allow_paid_models=self.settings.allow_paid_models,
            on_shift=self._handle_router_shift,
        )

    def _queue_ws_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._pending_events.append((event_type, payload))

    def _handle_router_shift(self, shift: RouterShiftEvent) -> None:
        self._queue_ws_event("router_shift", shift.model_dump())

    async def flush_events(self) -> None:
        while self._pending_events:
            ev_type, payload = self._pending_events.pop(0)
            await self.ws_manager.broadcast(ev_type, payload)

    async def set_state(self, state: str, detail: str = "") -> None:
        self.koda_state = state
        await self.ws_manager.broadcast("koda_state", {"state": state, "detail": detail})

    async def startup(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self.supervisor is not None:
            await self.supervisor.start(ready_timeout_sec=30.0)
        try:
            await self.router.refresh_models()
        except OpenCodeError:
            # Allow FastAPI to boot even if OpenCode starts slightly later or recovers via retry.
            pass

    async def _handle_voice_transcript(self, transcript: str) -> str:
        res = await self.chat(ChatRequest(prompt=transcript, conversation_id="voice"))
        return str(res.get("reply", ""))

    async def _resolve_approval_async(self, approval_id: str, approved: bool) -> bool:
        return self.safety.resolve_approval(approval_id, approved=approved)

    async def shutdown(self) -> None:
        await self.daemon.shutdown()
        await self.voice.stop_listening()
        await self.client.close()
        if self.supervisor is not None:
            self.supervisor.stop()

    def _build_system_preamble(self) -> str:
        base = (
            "You are Koda, a precise, concise Jarvis-class Windows AI assistant. "
            "Respect user preferences and workspace boundaries. Never fabricate tool results."
        )
        if self.tool_catalog_prompt:
            return (
                f"{base}\n\n{self.tool_catalog_prompt}\n"
                'To invoke a tool, output ONLY `<koda_tool>{"name": "<tool>", "args": {...}}</koda_tool>`.'
            )
        return base

    async def chat(self, req: ChatRequest) -> dict[str, Any]:
        await self.set_state("thinking", req.prompt[:80])
        extracted: list[dict[str, str]] = []
        for cat, key, val in extract_candidate_facts(req.prompt):
            rec = self.memory.upsert_fact(cat, key, val, source="auto")
            extracted.append({"category": rec.category, "key": rec.key, "value": rec.value})

        facts = self.memory.list_facts(limit=12)
        pinned_facts = [f"{f.key}: {f.value}" for f in facts]
        summary = self.memory.get_summary(req.conversation_id)
        turns = [{"role": t.role, "content": t.content} for t in self.memory.recent_turns(req.conversation_id, limit=8)]

        self.memory.record_episode(req.conversation_id, "user", req.prompt)

        current_prompt = req.prompt
        tool_events: list[dict[str, Any]] = []
        final_resp = None

        for _step in range(5):
            routed = await self.router.route_prompt(
                user_prompt=current_prompt,
                lane=req.lane,
                system_preamble=self._build_system_preamble(),
                conversation_id=req.conversation_id,
                pinned_facts=pinned_facts,
                rolling_summary=summary,
                recent_turns=turns,
                files=req.files,
                has_image=req.has_image,
                has_audio_or_video=req.has_audio_or_video,
                preferred_model_id=req.preferred_model_id,
            )
            await self.flush_events()
            final_resp = routed

            tool_match = _TOOL_TAG_RE.search(routed.text)
            if not tool_match or self.tool_executor is None:
                break

            try:
                tool_call = json.loads(tool_match.group(1))
                tool_name = str(tool_call.get("name", "")).strip()
                tool_args = dict(tool_call.get("args", {}) or {})
            except (json.JSONDecodeError, TypeError, ValueError):
                break

            decision = self.safety.evaluate(tool_name, tool_args)
            if decision.blocked:
                self.memory.log_audit(
                    actor="koda",
                    tool_name=tool_name,
                    tier=decision.tier.value,
                    decision="DENIED",
                    summary=decision.summary,
                    result_status="blocked",
                )
                tool_out: dict[str, Any] = {"ok": False, "blocked": True, "reason": decision.reason}
            elif decision.requires_confirmation:
                approval_id = f"apr_{uuid.uuid4().hex[:8]}"
                await self.set_state("confirm_needed", decision.summary)
                approved = await self.safety.await_approval(
                    approval_id=approval_id,
                    tool_name=tool_name,
                    args=tool_args,
                    summary=decision.summary,
                )
                await self.flush_events()
                if not approved:
                    self.memory.log_audit(
                        actor="user",
                        tool_name=tool_name,
                        tier=decision.tier.value,
                        decision="DENIED",
                        summary=decision.summary,
                        result_status="rejected",
                    )
                    tool_out = {"ok": False, "approved": False, "reason": "User denied action"}
                else:
                    tool_out = await self.tool_executor(tool_name, tool_args)
                    self.memory.log_audit(
                        actor="user",
                        tool_name=tool_name,
                        tier=decision.tier.value,
                        decision="APPROVED",
                        summary=decision.summary,
                        result_status="ok" if tool_out.get("ok", True) else "error",
                    )
            else:
                tool_out = await self.tool_executor(tool_name, tool_args)
                self.memory.log_audit(
                    actor="koda",
                    tool_name=tool_name,
                    tier=decision.tier.value,
                    decision="ALLOWED",
                    summary=decision.summary,
                    result_status="ok" if tool_out.get("ok", True) else "error",
                )

            ev_entry = {"tool": tool_name, "args": tool_args, "tier": decision.tier.value, "result": tool_out}
            tool_events.append(ev_entry)
            await self.ws_manager.broadcast("tool_event", ev_entry)
            current_prompt = (
                f"Original user request: {req.prompt}\n"
                f"Executed tool `{tool_name}` with result: {json.dumps(tool_out)[:3000]}\n"
                "Now give a clear, concise final answer to the user."
            )

        assert final_resp is not None
        self.memory.record_episode(
            req.conversation_id,
            "assistant",
            final_resp.text,
            model_id=final_resp.model_id,
            lane=final_resp.lane.value,
            tokens_in=final_resp.tokens_in,
            tokens_out=final_resp.tokens_out,
        )
        new_summary = update_rolling_summary(summary, req.prompt, final_resp.text)
        self.memory.set_summary(req.conversation_id, new_summary)

        payload = {
            "conversation_id": req.conversation_id,
            "reply": final_resp.text,
            "model_id": final_resp.model_id,
            "provider_id": final_resp.provider_id,
            "lane": final_resp.lane.value,
            "cost": final_resp.cost,
            "tokens_in": final_resp.tokens_in,
            "tokens_out": final_resp.tokens_out,
            "latency_ms": round(final_resp.latency_ms, 1),
            "shifted_from": final_resp.shifted_from,
            "shift_reason": final_resp.shift_reason,
            "extracted_facts": extracted,
            "tool_calls": tool_events,
        }
        await self.ws_manager.broadcast("chat_message", payload)
        await self.set_state("idle", final_resp.model_id)
        return payload

    def router_status_snapshot(self) -> dict[str, Any]:
        health_map = {h.model_id: h for h in self.telemetry.all_states()}
        models_out = []
        for m in self.router.pool:
            rec = health_map.get(m.id)
            eff = self.telemetry.effective_state(m.id)
            models_out.append(
                {
                    "id": m.id,
                    "provider_id": m.provider_id,
                    "input_capabilities": m.input_capabilities,
                    "tools": m.tools,
                    "state": eff.value,
                    "fail_count": rec.fail_count if rec else 0,
                    "ewma_latency_ms": round(rec.ewma_latency_ms, 1) if rec else 0.0,
                    "total_requests": rec.total_requests if rec else 0,
                    "total_tokens": (rec.total_tokens_in + rec.total_tokens_out) if rec else 0,
                    "cooldown_until": rec.cooldown_until if rec else 0.0,
                    "last_error": rec.last_error if rec else "",
                }
            )
        return {
            "allow_paid_models": self.settings.allow_paid_models,
            "free_models_count": len(self.router.pool),
            "models": models_out,
            "recent_shifts": [s.model_dump() for s in self.telemetry.recent_shifts(limit=25)],
        }


def create_app(service: KodaService | None = None) -> FastAPI:
    svc = service or KodaService()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await svc.startup()
        try:
            yield
        finally:
            await svc.shutdown()

    app = FastAPI(title="Koda AI OS", version="0.1.0", lifespan=lifespan)
    app.state.koda = svc

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8765"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        opencode_ok = False
        try:
            await svc.client.health()
            opencode_ok = True
        except OpenCodeError:
            opencode_ok = False
        return {
            "status": "ok",
            "state": svc.koda_state,
            "allow_paid_models": svc.settings.allow_paid_models,
            "free_models_count": len(svc.router.pool),
            "opencode_connected": opencode_ok,
        }

    @app.post("/api/chat")
    async def chat_endpoint(req: ChatRequest) -> dict[str, Any]:
        try:
            return await svc.chat(req)
        except AllFreeModelsExhaustedError as exc:
            await svc.set_state("idle", "all_models_cooldown")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": str(exc),
                    "retry_after_sec": round(exc.retry_after_sec, 1),
                    "attempted_models": exc.attempted_models,
                },
            ) from exc

    @app.get("/api/router/status")
    async def router_status() -> dict[str, Any]:
        return svc.router_status_snapshot()

    @app.post("/api/router/refresh")
    async def router_refresh() -> dict[str, Any]:
        models = await svc.router.refresh_models()
        return {"count": len(models), "models": [m.id for m in models]}

    @app.post("/api/router/models/{model_id}/state")
    async def router_model_toggle(model_id: str, req: ModelToggleRequest) -> dict[str, Any]:
        rec = svc.telemetry.set_disabled(model_id, req.disabled)
        await svc.ws_manager.broadcast("router_update", rec.model_dump())
        return rec.model_dump()

    @app.get("/api/memory/facts")
    async def list_facts() -> dict[str, Any]:
        return {"facts": [f.model_dump() for f in svc.memory.list_facts()]}

    @app.post("/api/memory/facts")
    async def create_fact(req: FactCreateRequest) -> dict[str, Any]:
        rec = svc.memory.upsert_fact(req.category, req.key, req.value, source="user")
        return rec.model_dump()

    @app.delete("/api/memory/facts/{fact_id}")
    async def delete_fact(fact_id: int) -> dict[str, Any]:
        deleted = svc.memory.delete_fact(fact_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Fact not found")
        return {"deleted": True, "id": fact_id}

    @app.get("/api/memory/search")
    async def search_memory(q: str = "") -> dict[str, Any]:
        return {
            "facts": [f.model_dump() for f in svc.memory.search_facts(q)],
            "episodes": [e.model_dump() for e in svc.memory.search_episodes(q)],
            "recall": [r.model_dump() for r in svc.memory.search_recall(query=q)],
        }

    @app.get("/api/approvals")
    async def list_approvals(status: str = "pending") -> dict[str, Any]:
        return {"approvals": [a.model_dump() for a in svc.memory.list_approvals(status=status)]}

    @app.post("/api/approvals/{approval_id}/resolve")
    async def resolve_approval(approval_id: str, req: ApprovalResolveRequest) -> dict[str, Any]:
        ok = svc.safety.resolve_approval(approval_id, approved=req.approved)
        if not ok:
            raise HTTPException(status_code=404, detail="Approval not found or already resolved")
        await svc.ws_manager.broadcast("approval_resolved", {"id": approval_id, "approved": req.approved})
        return {"id": approval_id, "approved": req.approved}

    @app.get("/api/audit")
    async def list_audit() -> dict[str, Any]:
        return {"entries": [a.model_dump() for a in svc.memory.list_audit_logs()]}

    @app.get("/api/clipboard")
    async def list_clipboard(q: str = "") -> dict[str, Any]:
        return {"items": [c.model_dump() for c in svc.memory.list_clipboard(query=q)]}

    @app.get("/api/routines")
    async def list_routines() -> dict[str, Any]:
        return {"routines": [r.model_dump() for r in svc.memory.list_routines()]}

    @app.post("/api/routines")
    async def upsert_routine(req: RoutineCreateRequest) -> dict[str, Any]:
        rec = svc.memory.upsert_routine(
            name=req.name,
            trigger_phrase=req.trigger_phrase,
            steps=req.steps,
            cron_expr=req.cron_expr,
            enabled=req.enabled,
        )
        return rec.model_dump()

    @app.get("/api/recall")
    async def list_recall(q: str = "") -> dict[str, Any]:
        return {"events": [e.model_dump() for e in svc.memory.search_recall(query=q)]}

    @app.get("/api/tools")
    async def list_tools() -> dict[str, Any]:
        return {"tools": svc.tool_registry.list_tools()}

    @app.post("/api/tools/run")
    async def run_tool(req: ToolRunRequest) -> dict[str, Any]:
        result = await svc.tool_registry.dispatch(req.name, req.args, approved=False)
        await svc.ws_manager.broadcast(
            "tool_event",
            {"tool": req.name, "args": req.args, "result": result},
        )
        return result

    @app.get("/api/voice/status")
    async def voice_status() -> dict[str, Any]:
        return {
            "wake_word": svc.settings.wake_word,
            "stt_model": svc.settings.stt_model,
            "tts_engine": svc.settings.tts_engine,
            "tts_voice": svc.settings.tts_voice,
            "listening": svc.voice.listening,
            "speaking": svc.voice.synthesizer.is_speaking,
            "dictation_mode": svc.voice.dictation_mode,
        }

    @app.post("/api/voice/barge-in")
    async def voice_barge_in() -> dict[str, Any]:
        svc.voice.barge_in()
        await svc.set_state("listening" if svc.voice.listening else "idle", "barge_in")
        return {"barge_in": True, "speaking": svc.voice.synthesizer.is_speaking}

    @app.post("/api/voice/speak")
    async def voice_speak(req: VoiceSpeakRequest) -> dict[str, Any]:
        asyncio.create_task(svc.voice.synthesizer.speak(req.text))
        return {"queued": True}

    @app.post("/api/voice/listen")
    async def voice_listen(req: VoiceToggleRequest) -> dict[str, Any]:
        if req.enabled:
            return await svc.voice.start_listening()
        return await svc.voice.stop_listening()

    @app.post("/api/voice/dictation")
    async def voice_dictation(req: VoiceToggleRequest) -> dict[str, Any]:
        svc.voice.dictation_mode = req.enabled
        return {"dictation_mode": svc.voice.dictation_mode}

    @app.post("/api/briefing")
    async def morning_briefing() -> dict[str, Any]:
        metrics = await svc.tool_registry.dispatch("system_metrics", {}, approved=True)
        prompt = MorningBriefingBuilder(memory=svc.memory).build_prompt_context(metrics=metrics)
        return await svc.chat(ChatRequest(prompt=prompt, conversation_id="briefing", lane=Lane.DEEP_1M))

    @app.post("/api/timers")
    async def create_timer(req: TimerCreateRequest) -> dict[str, Any]:
        svc.daemon.schedule_timer(req.label, delay_sec=req.delay_sec)
        return {"scheduled": True, "label": req.label, "delay_sec": req.delay_sec}

    @app.post("/api/recall/toggle")
    async def toggle_recall(req: VoiceToggleRequest) -> dict[str, Any]:
        svc.daemon.recall_enabled = req.enabled
        return {"recall_enabled": svc.daemon.recall_enabled}

    @app.get("/api/recall/status")
    async def recall_status() -> dict[str, Any]:
        return {"recall_enabled": svc.daemon.recall_enabled}

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await svc.ws_manager.connect(websocket)
        try:
            while True:
                msg = await websocket.receive_json()
                action = str(msg.get("action", "")).strip().lower()
                if action == "ping":
                    await websocket.send_json({"type": "pong", "ts": time.time()})
                elif action in ("approve", "deny"):
                    apr_id = str(msg.get("approval_id", ""))
                    svc.safety.resolve_approval(apr_id, approved=(action == "approve"))
                elif action == "barge_in" and svc._barge_in_hook is not None:
                    svc._barge_in_hook()
        except WebSocketDisconnect:
            svc.ws_manager.disconnect(websocket)

    dist_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist_dir.is_dir():
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="koda-assets")

        @app.get("/")
        async def serve_hud() -> FileResponse:
            return FileResponse(dist_dir / "index.html")

    return app
