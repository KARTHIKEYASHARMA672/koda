"""Async REST + SSE client for OpenCode v2.2.6 `/api/*` endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx
from pydantic import BaseModel, Field


class OpenCodeError(Exception):
    """Base exception for OpenCode communication or execution failures."""


class OpenCodeQuotaError(OpenCodeError):
    """Free-tier quota exhausted (HTTP 402 or `provider.quota`)."""


class OpenCodeRateLimitError(OpenCodeError):
    """Upstream rate limit reached (HTTP 429 or throttling message)."""


class OpenCodeContextOverflowError(OpenCodeError):
    """Prompt exceeded model context window."""


class OpenCodeTimeoutError(OpenCodeError):
    """Request or generation timed out."""


class OpenCodeExecutionError(OpenCodeError):
    """Transient model/server failure."""


class OpenCodePromptResult(BaseModel):
    """Normalized assistant completion returned by OpenCode `/api/session/{id}/message`."""

    session_id: str
    message_id: str = ""
    model_id: str
    text: str
    cost: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    raw_error: dict[str, Any] | None = Field(default=None)


def _classify_error(message: str, *, status_code: int | None = None, error_type: str = "") -> OpenCodeError:
    lower = f"{error_type} {message}".lower()
    if status_code == 402 or "provider.quota" in lower or "quota" in lower or "insufficient" in lower:
        return OpenCodeQuotaError(message or "Provider quota exhausted")
    if status_code == 429 or "rate limit" in lower or "too many requests" in lower or "throttl" in lower:
        return OpenCodeRateLimitError(message or "Rate limit exceeded")
    if "context" in lower and ("length" in lower or "window" in lower or "limit" in lower or "token" in lower):
        return OpenCodeContextOverflowError(message or "Context limit exceeded")
    if status_code in (408, 504) or "timeout" in lower or "timed out" in lower:
        return OpenCodeTimeoutError(message or "Execution timed out")
    return OpenCodeExecutionError(message or f"OpenCode execution failed (status={status_code})")


def _extract_text_parts(message: Mapping[str, Any]) -> str:
    parts = message.get("content")
    if isinstance(parts, list):
        chunks = [
            str(part.get("text", ""))
            for part in parts
            if isinstance(part, Mapping) and part.get("type") == "text" and part.get("text")
        ]
        if chunks:
            return "".join(chunks).strip()
    if isinstance(message.get("text"), str):
        return message["text"].strip()
    return ""


class OpenCodeClient:
    """Async client verified against `opencode.EXE serve` (`v2.2.6`)."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:4096",
        username: str = "opencode",
        password: str = "",
        timeout_sec: float = 45.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        auth = httpx.BasicAuth(username, password) if username else None
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=auth,
            timeout=httpx.Timeout(timeout_sec, connect=5.0),
            transport=transport,
        )

    async def __aenter__(self) -> OpenCodeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise OpenCodeTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise OpenCodeExecutionError(f"HTTP transport error on {method} {path}: {exc}") from exc

        if response.status_code >= 400:
            body_text = response.text[:400]
            raise _classify_error(body_text, status_code=response.status_code)
        return response

    async def health(self) -> dict[str, Any]:
        """Fast readiness probe (`GET /api/info`)."""
        resp = await self._request("GET", "/api/info")
        payload = resp.json()
        return dict(payload) if isinstance(payload, Mapping) else {}

    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch raw model catalog (`GET /api/model`)."""
        resp = await self._request("GET", "/api/model")
        payload = resp.json()
        data = payload.get("data", []) if isinstance(payload, Mapping) else []
        return [dict(item) for item in data if isinstance(item, Mapping)]

    async def create_session(self, title: str = "koda-session") -> str:
        """Create an OpenCode session and return its ID (`POST /api/session`)."""
        resp = await self._request("POST", "/api/session", json={"title": title})
        payload = resp.json()
        data = payload.get("data", {}) if isinstance(payload, Mapping) else {}
        session_id = str(data.get("id", "")).strip()
        if not session_id:
            raise OpenCodeExecutionError(f"OpenCode /api/session omitted data.id: {payload}")
        return session_id

    async def set_session_model(self, session_id: str, provider_id: str, model_id: str) -> None:
        """Bind exact `providerID` and `id` onto a session (`POST /api/session/{id}/model`)."""
        await self._request(
            "POST",
            f"/api/session/{session_id}/model",
            json={"model": {"providerID": provider_id, "id": model_id}},
        )

    async def prompt_session(
        self,
        session_id: str,
        text: str,
        *,
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send prompt text (and optional file paths) to an OpenCode session."""
        body: dict[str, Any] = {"text": text}
        if files:
            body["files"] = files
        resp = await self._request("POST", f"/api/session/{session_id}/prompt", json=body)
        payload = resp.json()
        data = payload.get("data", {}) if isinstance(payload, Mapping) else {}
        return dict(data) if isinstance(data, Mapping) else {}

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Retrieve messages for a session (`GET /api/session/{id}/message`)."""
        resp = await self._request("GET", f"/api/session/{session_id}/message")
        payload = resp.json()
        data = payload.get("data", []) if isinstance(payload, Mapping) else []
        return [dict(item) for item in data if isinstance(item, Mapping)]

    async def delete_session(self, session_id: str) -> None:
        """Clean up an ephemeral OpenCode session (`DELETE /api/session/{id}`)."""
        try:
            await self._request("DELETE", f"/api/session/{session_id}")
        except OpenCodeError:
            # Best-effort teardown so deletion never masks upstream prompt result/errors.
            return

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Stream live OpenCode Server-Sent Events (`GET /api/event`)."""
        try:
            async with self._client.stream("GET", "/api/event", timeout=None) as response:
                if response.status_code >= 400:
                    raw_body = (await response.aread()).decode(errors="ignore")
                    raise _classify_error(raw_body, status_code=response.status_code)
                event_name = "message"
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line == "":
                        if data_lines:
                            raw = "\n".join(data_lines)
                            try:
                                parsed = json.loads(raw)
                            except json.JSONDecodeError:
                                parsed = {"raw": raw}
                            yield {"event": event_name, "data": parsed}
                            event_name = "message"
                            data_lines.clear()
                        continue
                    if line.startswith("event:"):
                        event_name = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
        except httpx.HTTPError as exc:
            raise OpenCodeExecutionError(f"SSE stream error: {exc}") from exc

    async def _wait_for_assistant_reply(
        self,
        session_id: str,
        *,
        poll_timeout_sec: float = 40.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + poll_timeout_sec
        delay = 0.05
        while True:
            messages = await self.get_messages(session_id)
            assistant_msgs = [m for m in messages if m.get("type") == "assistant"]
            if assistant_msgs:
                latest = assistant_msgs[-1]
                finish = str(latest.get("finish", "")).strip().lower()
                error_obj = latest.get("error")
                time_obj = latest.get("time")
                completed = isinstance(time_obj, Mapping) and time_obj.get("completed") is not None
                text = _extract_text_parts(latest)
                if finish in ("stop", "error", "length", "tool-calls") or error_obj or completed or text:
                    return latest
            if time.monotonic() >= deadline:
                raise OpenCodeTimeoutError(f"Timed out waiting for assistant completion in {session_id}")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 0.5)

    async def run_single_prompt(
        self,
        provider_id: str,
        model_id: str,
        text: str,
        *,
        title: str = "koda",
        files: list[str] | None = None,
        poll_timeout_sec: float = 40.0,
    ) -> OpenCodePromptResult:
        """Execute one turn cleanly against an isolated session pinned to a chosen model."""
        started = time.perf_counter()
        session_id = await self.create_session(title=title)
        try:
            await self.set_session_model(session_id, provider_id, model_id)
            await self.prompt_session(session_id, text, files=files)
            latest = await self._wait_for_assistant_reply(session_id, poll_timeout_sec=poll_timeout_sec)

            error_obj = latest.get("error")
            finish = str(latest.get("finish", "")).strip().lower()
            if isinstance(error_obj, Mapping):
                raise _classify_error(
                    str(error_obj.get("message", "")),
                    status_code=error_obj.get("status") if isinstance(error_obj.get("status"), int) else None,
                    error_type=str(error_obj.get("type", "")),
                )
            if finish == "error":
                raise OpenCodeExecutionError("OpenCode assistant finished with error status")

            reply_text = _extract_text_parts(latest)
            if not reply_text:
                raise OpenCodeExecutionError(f"Empty assistant text returned by {model_id}")

            tokens = latest.get("tokens")
            tokens_map = tokens if isinstance(tokens, Mapping) else {}
            cost_val = float(latest.get("cost", 0.0) or 0.0)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return OpenCodePromptResult(
                session_id=session_id,
                message_id=str(latest.get("id", "")),
                model_id=model_id,
                text=reply_text,
                cost=cost_val,
                tokens_in=int(tokens_map.get("input", 0) or 0),
                tokens_out=int(tokens_map.get("output", 0) or 0),
                latency_ms=elapsed_ms,
            )
        finally:
            await self.delete_session(session_id)
