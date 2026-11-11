from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from koda.opencode.client import (
    OpenCodePromptResult,
    OpenCodeQuotaError,
    OpenCodeTimeoutError,
)
from koda.opencode.models import Lane, OpenCodeModelInfo
from koda.router.engine import AllFreeModelsExhaustedError, FreeModelRouter, RouterShiftEvent
from koda.router.state import CircuitState, RouterTelemetryStore


def _model(model_id: str, *, caps: list[str] | None = None) -> OpenCodeModelInfo:
    return OpenCodeModelInfo(
        id=model_id,
        provider_id="opencode",
        name=model_id,
        input_capabilities=caps or ["text"],
        tools=True,
        context_limit=128000,
    )


def test_circuit_breaker_transitions_and_persists_in_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "koda.db"
    now = [1000.0]

    store = RouterTelemetryStore(db_path=db_path, clock=lambda: now[0], base_cooldown_sec=30.0)
    assert store.get_state("iceman-free").state == CircuitState.HEALTHY

    # First transient timeout -> SOFT_SHIFTED
    s1 = store.record_failure("iceman-free", reason="timeout", hard_quota=False)
    assert s1.state == CircuitState.SOFT_SHIFTED
    assert s1.cooldown_until == 0.0

    # Second failure -> COOLDOWN (30s)
    s2 = store.record_failure("iceman-free", reason="timeout", hard_quota=False)
    assert s2.state == CircuitState.COOLDOWN
    assert s2.cooldown_until == pytest.approx(1030.0)

    # Re-open SQLite from disk to verify persistence across daemon restarts
    reloaded = RouterTelemetryStore(db_path=db_path, clock=lambda: now[0], base_cooldown_sec=30.0)
    assert reloaded.effective_state("iceman-free") == CircuitState.COOLDOWN

    # Advance past cooldown -> HALF_OPEN
    now[0] = 1031.0
    assert reloaded.effective_state("iceman-free") == CircuitState.HALF_OPEN

    # Probe succeeds -> HEALTHY with EWMA latency updated
    reloaded.record_success("iceman-free", latency_ms=220.0, tokens_in=50, tokens_out=20)
    recovered = reloaded.get_state("iceman-free")
    assert recovered.state == CircuitState.HEALTHY
    assert recovered.fail_count == 0
    assert recovered.ewma_latency_ms == pytest.approx(220.0)


def test_router_shifts_model_on_quota_exhaustion_with_context_handoff(tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []
    shifts: list[RouterShiftEvent] = []

    class FakeClient:
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
            calls.append((model_id, text))
            if model_id == "iceman-free":
                raise OpenCodeQuotaError("402 quota exhausted")
            return OpenCodePromptResult(
                session_id="ses_next",
                message_id="msg_2",
                model_id=model_id,
                text="Switched cleanly and verified.",
                cost=0.0,
                tokens_in=140,
                tokens_out=25,
                latency_ms=310.0,
            )

    store = RouterTelemetryStore(db_path=tmp_path / "koda.db")
    router = FreeModelRouter(
        client=FakeClient(),  # type: ignore[arg-type]
        telemetry=store,
        on_shift=shifts.append,
    )

    async def run() -> None:
        await router.refresh_models()
        result = await router.route_prompt(
            user_prompt="Summarize my morning schedule",
            lane=Lane.FAST,
            conversation_id="conv_1",
            pinned_facts=["User prefers concise bulleted summaries"],
            rolling_summary="Discussed calendar setup earlier.",
            recent_turns=[
                {"role": "user", "content": "Check my tasks"},
                {"role": "assistant", "content": "You have 2 tasks pending."},
            ],
        )

        assert result.model_id == "nemotron-3.5-lightning-free"
        assert result.cost == 0.0
        assert result.text == "Switched cleanly and verified."
        assert result.shifted_from == "iceman-free"

    asyncio.run(run())

    assert len(calls) == 2
    assert calls[0][0] == "iceman-free"
    assert calls[1][0] == "nemotron-3.5-lightning-free"
    # Verify handoff prompt preserved pinned facts, rolling summary, and recent turns
    handoff_prompt = calls[1][1]
    assert "User prefers concise bulleted summaries" in handoff_prompt
    assert "Discussed calendar setup earlier." in handoff_prompt
    assert "Check my tasks" in handoff_prompt
    assert "Summarize my morning schedule" in handoff_prompt

    assert len(shifts) == 1
    assert shifts[0].from_model == "iceman-free"
    assert shifts[0].to_model == "nemotron-3.5-lightning-free"
    assert store.effective_state("iceman-free") == CircuitState.COOLDOWN
    assert len(store.recent_shifts(limit=5)) == 1


def test_router_raises_bounded_error_when_all_free_models_exhausted(tmp_path: Path) -> None:
    attempts = 0

    class AlwaysFailClient:
        async def list_models(self) -> list[dict]:
            return [
                {
                    "id": "iceman-free",
                    "providerID": "opencode",
                    "cost": [{"input": 0, "output": 0}],
                    "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
                },
                {
                    "id": "beam-free",
                    "providerID": "opencode",
                    "cost": [{"input": 0, "output": 0}],
                    "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
                },
            ]

        async def run_single_prompt(self, *args, **kwargs) -> OpenCodePromptResult:
            nonlocal attempts
            attempts += 1
            raise OpenCodeTimeoutError("upstream timed out")

    store = RouterTelemetryStore(db_path=tmp_path / "koda.db")
    router = FreeModelRouter(client=AlwaysFailClient(), telemetry=store, max_attempts=3)  # type: ignore[arg-type]

    async def run() -> None:
        await router.refresh_models()
        with pytest.raises(AllFreeModelsExhaustedError):
            await router.route_prompt(user_prompt="hello", lane=Lane.FAST)

    asyncio.run(run())
    # Bounded by available pool size (2 models), never infinite loop
    assert attempts == 2


def test_telemetry_store_releases_sqlite_file_handles_on_windows(tmp_path: Path) -> None:
    db_path = tmp_path / "ephemeral.db"
    store = RouterTelemetryStore(db_path=db_path)
    store.record_success("iceman-free", latency_ms=100.0)
    db_path.unlink()
    assert not db_path.exists()
