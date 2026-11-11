from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from koda.opencode.client import (
    OpenCodeClient,
    OpenCodeQuotaError,
    OpenCodeRateLimitError,
    OpenCodeTimeoutError,
)
from koda.opencode.supervisor import OpenCodeSupervisor


def test_client_enforces_exact_v226_api_contract() -> None:
    captured: list[tuple[str, str, dict | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else None
        captured.append((request.method, request.url.path, body, request.headers.get("authorization")))

        if request.method == "GET" and request.url.path == "/api/info":
            return httpx.Response(200, json={"version": "2.2.6"})
        if request.method == "GET" and request.url.path == "/api/model":
            return httpx.Response(200, json={"data": [{"id": "iceman-free", "providerID": "opencode", "cost": [{"input": 0, "output": 0}]}]})
        if request.method == "POST" and request.url.path == "/api/session":
            return httpx.Response(200, json={"data": {"id": "ses_test123", "title": "koda"}})
        if request.method == "POST" and request.url.path == "/api/session/ses_test123/model":
            assert body == {"model": {"providerID": "opencode", "id": "iceman-free"}}
            return httpx.Response(204)
        if request.method == "POST" and request.url.path == "/api/session/ses_test123/prompt":
            assert body == {"text": "ping"}
            return httpx.Response(200, json={"data": {"id": "msg_1"}})
        if request.method == "GET" and request.url.path == "/api/session/ses_test123/message":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "msg_u", "type": "user", "content": [{"type": "text", "text": "ping"}]},
                        {
                            "id": "msg_a",
                            "type": "assistant",
                            "finish": "stop",
                            "cost": 0,
                            "tokens": {"input": 12, "output": 4},
                            "content": [{"type": "text", "text": "KODA_ONLINE"}],
                        },
                    ]
                },
            )
        if request.method == "DELETE" and request.url.path == "/api/session/ses_test123":
            return httpx.Response(204)
        return httpx.Response(404, json={"error": "unexpected path"})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=transport,
        ) as client:
            info = await client.health()
            assert info["version"] == "2.2.6"

            models = await client.list_models()
            assert len(models) == 1

            result = await client.run_single_prompt(
                provider_id="opencode",
                model_id="iceman-free",
                text="ping",
                title="koda-test",
            )
            assert result.text == "KODA_ONLINE"
            assert result.cost == 0.0
            assert result.tokens_in == 12
            assert result.tokens_out == 4

    asyncio.run(run())
    assert all(auth and auth.startswith("Basic ") for _, _, _, auth in captured)
    assert any(method == "DELETE" and path == "/api/session/ses_test123" for method, path, _, _ in captured)


def test_client_detects_provider_quota_and_rate_limit_errors() -> None:
    def quota_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session":
            return httpx.Response(200, json={"data": {"id": "ses_q"}})
        if request.url.path.endswith("/model"):
            return httpx.Response(204)
        if request.url.path.endswith("/prompt"):
            return httpx.Response(200, json={"data": {"id": "msg_q"}})
        if request.url.path.endswith("/message"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "msg_err",
                            "type": "assistant",
                            "finish": "error",
                            "error": {
                                "type": "provider.quota",
                                "status": 402,
                                "message": "Free quota exhausted for this model",
                            },
                            "content": [],
                        }
                    ]
                },
            )
        return httpx.Response(204)

    async def run_quota() -> None:
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=httpx.MockTransport(quota_handler),
        ) as client:
            with pytest.raises(OpenCodeQuotaError):
                await client.run_single_prompt("opencode", "iceman-free", "hello")

    asyncio.run(run_quota())

    def rate_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session":
            return httpx.Response(200, json={"data": {"id": "ses_r"}})
        if request.url.path.endswith("/model"):
            return httpx.Response(204)
        if request.url.path.endswith("/prompt"):
            return httpx.Response(429, json={"error": "rate limit exceeded"})
        return httpx.Response(204)

    async def run_rate() -> None:
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=httpx.MockTransport(rate_handler),
        ) as client:
            with pytest.raises(OpenCodeRateLimitError):
                await client.run_single_prompt("opencode", "iceman-free", "hello")

    asyncio.run(run_rate())


def test_client_maps_httpx_timeout_to_opencode_timeout() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/session":
            return httpx.Response(200, json={"data": {"id": "ses_t"}})
        if request.url.path.endswith("/model"):
            return httpx.Response(204)
        if request.url.path.endswith("/prompt"):
            raise httpx.ReadTimeout("stream stalled")
        return httpx.Response(204)

    async def run() -> None:
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=httpx.MockTransport(timeout_handler),
        ) as client:
            with pytest.raises(OpenCodeTimeoutError):
                await client.run_single_prompt("opencode", "iceman-free", "hello")

    asyncio.run(run())


def test_supervisor_builds_safe_command_and_env(tmp_path: Path) -> None:
    fake_exe = tmp_path / "opencode.EXE"
    fake_exe.write_text("", encoding="utf-8")

    sup = OpenCodeSupervisor(
        exe_path=fake_exe,
        host="127.0.0.1",
        port=4096,
        username="opencode",
        password="local_pw",
    )

    cmd = sup.build_command()
    env = sup.build_env()

    assert cmd == [str(fake_exe), "serve", "--hostname", "127.0.0.1", "--port", "4096"]
    assert env["OPENCODE_SERVER_USERNAME"] == "opencode"
    assert env["OPENCODE_SERVER_PASSWORD"] == "local_pw"


def test_client_stream_events_handles_sse_and_http_errors() -> None:
    def sse_handler(request: httpx.Request) -> httpx.Response:
        body = (
            "event: session.text.delta\n"
            'data: {"sessionID":"ses_1","delta":"hello"}\n\n'
        )
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async def run() -> list[dict]:
        events: list[dict] = []
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=httpx.MockTransport(sse_handler),
        ) as client:
            async for ev in client.stream_events():
                events.append(ev)
        return events

    events = asyncio.run(run())
    assert events == [{"event": "session.text.delta", "data": {"sessionID": "ses_1", "delta": "hello"}}]

    def err_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"rate limited")

    async def run_err() -> None:
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=httpx.MockTransport(err_handler),
        ) as client:
            with pytest.raises(OpenCodeRateLimitError):
                async for _ in client.stream_events():
                    pass

    asyncio.run(run_err())


def test_supervisor_waits_for_models_ready_not_just_info(tmp_path: Path) -> None:
    calls = {"info": 0, "model": 0}

    def booting_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/info":
            calls["info"] += 1
            return httpx.Response(200, json={"version": "2.2.6"})
        if request.url.path == "/api/model":
            calls["model"] += 1
            if calls["model"] < 2:
                return httpx.Response(
                    503,
                    json={"_tag": "ServiceUnavailableError", "message": "Location plugins did not finish activating"},
                )
            return httpx.Response(200, json={"data": [{"id": "iceman-free", "providerID": "opencode"}]})
        return httpx.Response(404)

    async def run() -> None:
        sup = OpenCodeSupervisor(exe_path=tmp_path / "opencode.EXE")
        async with OpenCodeClient(
            base_url="http://127.0.0.1:4096",
            username="opencode",
            password="pw",
            transport=httpx.MockTransport(booting_handler),
        ) as client:
            ready = await sup.is_ready(client)
            assert ready is False
            ready2 = await sup.is_ready(client)
            assert ready2 is True

    asyncio.run(run())
    assert calls["model"] == 2
