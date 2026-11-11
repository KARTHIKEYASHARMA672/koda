from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from koda.config import KodaSettings
from koda.gateway.app import ChatRequest, KodaService, create_app
from koda.opencode.client import OpenCodePromptResult, OpenCodeQuotaError


class StubOpenCodeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def health(self) -> dict:
        return {"version": "2.2.6"}

    async def list_models(self) -> list[dict]:
        return [
            {
                "id": "iceman-free",
                "providerID": "opencode",
                "cost": [{"input": 0, "output": 0}],
                "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
            },
            {
                "id": "nemotron-3.5-lightning-free",
                "providerID": "opencode",
                "cost": [{"input": 0, "output": 0}],
                "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
            },
        ]

    async def run_single_prompt(
        self,
        provider_id: str,
        model_id: str,
        text: str,
        title: str = "koda",
        files: list[str] | None = None,
    ) -> OpenCodePromptResult:
        self.calls.append(model_id)
        if model_id == "iceman-free" and "trigger_failover" in text:
            raise OpenCodeQuotaError("402 quota exhausted")
        return OpenCodePromptResult(
            session_id="ses_stub",
            message_id="msg_stub",
            model_id=model_id,
            text="Hello Karthikeya, zero-cost systems are online.",
            cost=0.0,
            tokens_in=50,
            tokens_out=12,
            latency_ms=120.0,
        )

    async def close(self) -> None:
        return None


def test_gateway_chat_memory_failover_and_websocket(tmp_path: Path) -> None:
    settings = KodaSettings(
        _env_file=None,
        data_dir=tmp_path,
        allowed_roots_raw=str(tmp_path),
    )
    service = KodaService(settings=settings, client=StubOpenCodeClient(), managed_opencode=False)  # type: ignore[arg-type]
    app = create_app(service)

    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["allow_paid_models"] is False
        assert h.json()["free_models_count"] == 2

        with client.websocket_connect("/ws/events") as ws:
            # First chat stores a user fact automatically and triggers quota failover
            resp = client.post(
                "/api/chat",
                json={
                    "prompt": "My name is Karthikeya. Please test trigger_failover.",
                    "conversation_id": "conv_main",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["cost"] == 0.0
            assert data["model_id"] == "nemotron-3.5-lightning-free"
            assert data["shifted_from"] == "iceman-free"

            # WebSocket receives koda_state(thinking), router_shift, chat_message, koda_state(idle)
            events = [ws.receive_json() for _ in range(4)]
            event_types = {e["type"] for e in events}
            assert "koda_state" in event_types
            assert "router_shift" in event_types
            assert "chat_message" in event_types

        facts_resp = client.get("/api/memory/facts")
        assert facts_resp.status_code == 200
        assert any(f["value"] == "Karthikeya" for f in facts_resp.json()["facts"])

        router_resp = client.get("/api/router/status")
        assert router_resp.status_code == 200
        assert len(router_resp.json()["recent_shifts"]) == 1

        tools_resp = client.get("/api/tools")
        assert tools_resp.status_code == 200
        tools_by_name = {t["name"]: t["tier"] for t in tools_resp.json()["tools"]}
        assert {"system_metrics", "browser_open", "save_note", "read_file", "run_shell"} <= set(tools_by_name)
        assert tools_by_name["system_metrics"] == "AUTO"
        assert tools_by_name["open_app"] == "NOTIFY"
        assert tools_by_name["write_file"] == "CONFIRM"
        assert tools_by_name["run_shell"] == "CONFIRM"


def test_gateway_tool_loop_enforces_hitl_approval_and_audit(tmp_path: Path) -> None:
    executed: list[tuple[str, dict]] = []

    class ToolLoopClient(StubOpenCodeClient):
        def __init__(self) -> None:
            super().__init__()
            self.turn = 0

        async def run_single_prompt(
            self,
            provider_id: str,
            model_id: str,
            text: str,
            title: str = "koda",
            files: list[str] | None = None,
        ) -> OpenCodePromptResult:
            self.turn += 1
            if self.turn == 1:
                return OpenCodePromptResult(
                    session_id="ses_1",
                    message_id="m1",
                    model_id=model_id,
                    text='<koda_tool>{"name": "run_shell", "args": {"command": "git status"}}</koda_tool>',
                    cost=0.0,
                )
            return OpenCodePromptResult(
                session_id="ses_2",
                message_id="m2",
                model_id=model_id,
                text="Working tree is clean.",
                cost=0.0,
            )

    async def fake_executor(tool_name: str, args: dict) -> dict:
        executed.append((tool_name, args))
        return {"ok": True, "stdout": "nothing to commit"}

    import asyncio

    settings = KodaSettings(_env_file=None, data_dir=tmp_path, allowed_roots_raw=str(tmp_path))
    service = KodaService(
        settings=settings,
        client=ToolLoopClient(),  # type: ignore[arg-type]
        managed_opencode=False,
        tool_executor=fake_executor,
        tool_catalog_prompt="Available: run_shell",
    )

    async def run() -> dict:
        await service.startup()
        try:
            chat_task = asyncio.create_task(
                service.chat(ChatRequest(prompt="Check git status", conversation_id="conv_tool"))
            )
            await asyncio.sleep(0.05)
            pending = service.memory.list_approvals(status="pending")
            assert len(pending) == 1
            assert executed == []
            service.safety.resolve_approval(pending[0].id, approved=True)
            return await chat_task
        finally:
            await service.shutdown()

    result = asyncio.run(run())
    assert result["reply"] == "Working tree is clean."
    assert executed == [("run_shell", {"command": "git status"})]
    assert len(service.memory.list_audit_logs()) == 1


def test_gateway_proactive_briefing_timers_recall_and_hud_static(tmp_path: Path) -> None:
    settings = KodaSettings(
        _env_file=None,
        data_dir=tmp_path,
        allowed_roots_raw=str(tmp_path),
    )
    service = KodaService(settings=settings, client=StubOpenCodeClient(), managed_opencode=False)  # type: ignore[arg-type]
    app = create_app(service)

    with TestClient(app) as client:
        # Built SPA HUD served from frontend/dist when present
        dist_index = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "index.html"
        if dist_index.is_file():
            home = client.get("/")
            assert home.status_code == 200
            assert "KODA" in home.text

        # Recall toggle
        st1 = client.get("/api/recall/status")
        assert st1.status_code == 200
        assert st1.json()["recall_enabled"] is False

        tg = client.post("/api/recall/toggle", json={"enabled": True})
        assert tg.status_code == 200
        assert tg.json()["recall_enabled"] is True

        # Timers endpoint
        tm = client.post("/api/timers", json={"label": "Check build", "delay_sec": 0.05})
        assert tm.status_code == 200
        assert tm.json()["scheduled"] is True

        # Briefing endpoint (uses DEEP_1M lane on free OpenCode models)
        br = client.post("/api/briefing")
        assert br.status_code == 200
        assert br.json()["cost"] == 0.0

        # Disable/re-enable model
        dis = client.post("/api/router/models/iceman-free/state", json={"disabled": True})
        assert dis.status_code == 200
        assert dis.json()["state"] == "DISABLED"
        ena = client.post("/api/router/models/iceman-free/state", json={"disabled": False})
        assert ena.status_code == 200
        assert ena.json()["state"] == "HEALTHY"
