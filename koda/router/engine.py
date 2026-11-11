"""Automatic zero-cost model router with quota failover and context handoff."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from koda.opencode.client import (
    OpenCodeClient,
    OpenCodeContextOverflowError,
    OpenCodeError,
    OpenCodeQuotaError,
    OpenCodeRateLimitError,
)
from koda.opencode.models import (
    LANE_FALLBACK_ORDER,
    Lane,
    OpenCodeModelInfo,
    classify_lane_for_request,
    filter_free_models,
    rank_models_for_lane,
)
from koda.router.state import CircuitState, RouterTelemetryStore

logger = logging.getLogger(__name__)


class AllFreeModelsExhaustedError(RuntimeError):
    """Raised when every permitted zero-cost OpenCode model is in cooldown or failed."""

    def __init__(self, message: str, *, retry_after_sec: float = 0.0, attempted_models: list[str] | None = None) -> None:
        super().__init__(message)
        self.retry_after_sec = retry_after_sec
        self.attempted_models = attempted_models or []


class RouterShiftEvent(BaseModel):
    """Live telemetry notification emitted whenever Koda fails over across models."""

    from_model: str
    to_model: str
    reason: str
    lane: Lane
    conversation_id: str = ""


class RoutedResponse(BaseModel):
    """Completed model response with routing and zero-cost telemetry."""

    model_id: str
    provider_id: str
    lane: Lane
    text: str
    cost: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    shifted_from: str | None = None
    shift_reason: str | None = None
    attempts: int = 1
    attempted_models: list[str] = Field(default_factory=list)


def build_handoff_prompt(
    *,
    user_prompt: str,
    system_preamble: str = "",
    pinned_facts: Sequence[str] = (),
    rolling_summary: str = "",
    recent_turns: Sequence[Mapping[str, Any]] = (),
    shifted_from: str | None = None,
    compact_mode: bool = False,
) -> str:
    """Assemble a self-contained prompt preserving user memory & recent context across model shifts."""
    sections: list[str] = []
    if system_preamble.strip():
        sections.append(system_preamble.strip())

    if shifted_from:
        sections.append(
            f"[CONTINUITY NOTICE] Continuing seamlessly after automatic failover from `{shifted_from}`. "
            "Do not mention internal error mechanics unless helpful; answer the user directly."
        )

    if pinned_facts:
        facts_limit = 6 if compact_mode else 12
        fact_lines = "\n".join(f"- {fact}" for fact in pinned_facts[:facts_limit])
        sections.append(f"## Known User Memory & Preferences\n{fact_lines}")

    if rolling_summary.strip():
        max_sum = 800 if compact_mode else 2400
        sections.append(f"## Conversation Summary\n{rolling_summary.strip()[:max_sum]}")

    if recent_turns:
        turn_slice = recent_turns[-3:] if compact_mode else recent_turns[-8:]
        turn_lines = []
        for turn in turn_slice:
            role = str(turn.get("role", "user")).upper()
            content = str(turn.get("content", "")).strip()
            if content:
                cap = 400 if compact_mode else 1200
                turn_lines.append(f"{role}: {content[:cap]}")
        if turn_lines:
            sections.append("## Recent Conversation Turns\n" + "\n".join(turn_lines))

    sections.append(f"## Current User Request\n{user_prompt}")
    return "\n\n".join(sections)


class FreeModelRouter:
    """Routes prompts strictly through verified $0 OpenCode models with automatic failover."""

    def __init__(
        self,
        *,
        client: OpenCodeClient,
        telemetry: RouterTelemetryStore,
        allow_google_free: bool = False,
        allow_paid_models: bool = False,
        max_attempts: int = 5,
        on_shift: Callable[[RouterShiftEvent], Any] | None = None,
    ) -> None:
        self.client = client
        self.telemetry = telemetry
        self.allow_google_free = allow_google_free
        self.allow_paid_models = allow_paid_models
        self.max_attempts = max_attempts
        self.on_shift = on_shift
        self.pool: list[OpenCodeModelInfo] = []

    async def refresh_models(self) -> list[OpenCodeModelInfo]:
        raw = await self.client.list_models()
        self.pool = filter_free_models(
            raw,
            allow_google_free=self.allow_google_free,
            allow_paid_models=self.allow_paid_models,
        )
        return list(self.pool)

    def _telemetry_rank_map(self) -> tuple[dict[str, tuple[int, float]], set[str]]:
        scores: dict[str, tuple[int, float]] = {}
        excluded: set[str] = set()
        for model in self.pool:
            eff = self.telemetry.effective_state(model.id)
            rec = self.telemetry.get_state(model.id)
            if eff in (CircuitState.COOLDOWN, CircuitState.DISABLED):
                excluded.add(model.id)
                continue
            rank = {
                CircuitState.HEALTHY: 0,
                CircuitState.HALF_OPEN: 1,
                CircuitState.SOFT_SHIFTED: 2,
            }.get(eff, 3)
            scores[model.id] = (rank, rec.ewma_latency_ms)
        return scores, excluded

    def select_candidates(self, lane: Lane, *, preferred_model_id: str | None = None) -> list[OpenCodeModelInfo]:
        scores, excluded = self._telemetry_rank_map()
        active_pool = [m for m in self.pool if m.id not in excluded]
        ordered: list[OpenCodeModelInfo] = []
        seen: set[str] = set()

        for target_lane in (lane, *LANE_FALLBACK_ORDER[lane]):
            for candidate in rank_models_for_lane(active_pool, target_lane, telemetry_scores=scores):
                if candidate.id not in seen:
                    ordered.append(candidate)
                    seen.add(candidate.id)

        if preferred_model_id:
            pinned = [m for m in ordered if m.id == preferred_model_id]
            rest = [m for m in ordered if m.id != preferred_model_id]
            ordered = pinned + rest
        return ordered

    async def route_prompt(
        self,
        *,
        user_prompt: str,
        lane: Lane | None = None,
        system_preamble: str = "",
        conversation_id: str = "",
        pinned_facts: Sequence[str] = (),
        rolling_summary: str = "",
        recent_turns: Sequence[Mapping[str, Any]] = (),
        files: list[str] | None = None,
        has_image: bool = False,
        has_audio_or_video: bool = False,
        preferred_model_id: str | None = None,
    ) -> RoutedResponse:
        if not self.pool:
            await self.refresh_models()

        target_lane = lane or classify_lane_for_request(
            user_prompt,
            has_image=has_image,
            has_audio_or_video=has_audio_or_video,
            context_chars=len(rolling_summary) + sum(len(str(t.get("content", ""))) for t in recent_turns),
        )
        candidates = self.select_candidates(target_lane, preferred_model_id=preferred_model_id)
        if not candidates:
            wait_sec = self.telemetry.earliest_retry_after_sec([m.id for m in self.pool])
            raise AllFreeModelsExhaustedError(
                f"No healthy $0 OpenCode models available for lane '{target_lane.value}'.",
                retry_after_sec=wait_sec,
            )

        attempt_limit = min(len(candidates), self.max_attempts)
        attempted: list[str] = []
        last_error_reason = ""
        first_failed_model: str | None = None
        first_fail_reason: str | None = None
        compact_mode = False

        for idx, candidate in enumerate(candidates[:attempt_limit]):
            if idx > 0 and first_failed_model is not None:
                shift_event = RouterShiftEvent(
                    from_model=attempted[-1],
                    to_model=candidate.id,
                    reason=last_error_reason,
                    lane=target_lane,
                    conversation_id=conversation_id,
                )
                self.telemetry.record_shift(
                    from_model=shift_event.from_model,
                    to_model=shift_event.to_model,
                    reason=shift_event.reason,
                    lane=target_lane.value,
                    conversation_id=conversation_id,
                )
                if self.on_shift is not None:
                    self.on_shift(shift_event)

            prompt_text = build_handoff_prompt(
                user_prompt=user_prompt,
                system_preamble=system_preamble,
                pinned_facts=pinned_facts,
                rolling_summary=rolling_summary,
                recent_turns=recent_turns,
                shifted_from=attempted[-1] if attempted else None,
                compact_mode=compact_mode,
            )

            attempted.append(candidate.id)
            try:
                res = await self.client.run_single_prompt(
                    candidate.provider_id,
                    candidate.id,
                    prompt_text,
                    title=f"koda-{target_lane.value}",
                    files=files,
                )
                if res.cost > 0 and not self.allow_paid_models:
                    raise OpenCodeQuotaError(f"Non-zero cost reported ({res.cost}) under strict $0 policy")

                self.telemetry.record_success(
                    candidate.id,
                    latency_ms=res.latency_ms,
                    tokens_in=res.tokens_in,
                    tokens_out=res.tokens_out,
                )
                return RoutedResponse(
                    model_id=candidate.id,
                    provider_id=candidate.provider_id,
                    lane=target_lane,
                    text=res.text,
                    cost=res.cost,
                    tokens_in=res.tokens_in,
                    tokens_out=res.tokens_out,
                    latency_ms=res.latency_ms,
                    shifted_from=first_failed_model,
                    shift_reason=first_fail_reason,
                    attempts=len(attempted),
                    attempted_models=attempted,
                )
            except OpenCodeError as exc:
                last_error_reason = str(exc) or type(exc).__name__
                if first_failed_model is None:
                    first_failed_model = candidate.id
                    first_fail_reason = last_error_reason
                hard_quota = isinstance(exc, (OpenCodeQuotaError, OpenCodeRateLimitError))
                if isinstance(exc, OpenCodeContextOverflowError):
                    compact_mode = True
                self.telemetry.record_failure(candidate.id, reason=last_error_reason, hard_quota=hard_quota)
                logger.warning("OpenCode model %s failed (%s); shifting if candidate remains", candidate.id, last_error_reason)

        wait_sec = self.telemetry.earliest_retry_after_sec([m.id for m in self.pool])
        raise AllFreeModelsExhaustedError(
            f"All attempted free models exhausted/failed ({', '.join(attempted)}): {last_error_reason}",
            retry_after_sec=wait_sec,
            attempted_models=attempted,
        )
