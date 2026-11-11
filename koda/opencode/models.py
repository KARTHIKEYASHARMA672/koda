"""Strict zero-cost OpenCode model filtering and 4-lane routing taxonomy."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Lane(StrEnum):
    """Semantic workload lanes for Koda's multi-model router."""

    FAST = "fast"
    VISION = "vision"
    DEEP_1M = "deep_1m"
    MULTIMODAL = "multimodal"


LANE_PREFERENCES: dict[Lane, tuple[str, ...]] = {
    Lane.FAST: (
        "iceman-free",
        "nemotron-3.5-lightning-free",
        "flint-40b-free",
        "beam-free",
        "big-pickle",
        "deepseek-v4.1-flash-free",
        "minimax-m3.1-flash-free",
        "glm-5.3-flash-free",
        "longcat-2.5-free",
        "inkling-2-small-free",
    ),
    Lane.VISION: (
        "nemotron-3.5-super-vl-free",
        "deepseek-v4.1-flash-free",
        "mimo-v2.6-flash-free",
        "minimax-m3.1-flash-free",
        "glm-5.3-flash-free",
        "inkling-2-small-free",
        "longcat-2.5-free",
    ),
    Lane.DEEP_1M: (
        "nemotron-3.5-lightning-free",
        "minimax-m3.1-flash-free",
        "glm-5.3-flash-free",
        "deepseek-v4.1-flash-free",
        "big-pickle",
        "flint-40b-free",
        "iceman-free",
    ),
    Lane.MULTIMODAL: (
        "mimo-v2.6-flash-free",
        "minimax-m3.1-flash-free",
        "glm-5.3-flash-free",
    ),
}

LANE_FALLBACK_ORDER: dict[Lane, tuple[Lane, ...]] = {
    Lane.FAST: (Lane.DEEP_1M, Lane.VISION, Lane.MULTIMODAL),
    Lane.DEEP_1M: (Lane.FAST, Lane.VISION, Lane.MULTIMODAL),
    Lane.VISION: (Lane.MULTIMODAL,),
    Lane.MULTIMODAL: (Lane.VISION,),
}

_DEEP_KEYWORDS = (
    "architecture",
    "analyze",
    "refactor",
    "deep dive",
    "codebase",
    "summarize document",
    "compare",
    "multi-file",
)


class OpenCodeModelInfo(BaseModel):
    """Normalized metadata for a vetted OpenCode model."""

    id: str
    provider_id: str = "opencode"
    name: str = ""
    input_capabilities: list[str] = Field(default_factory=lambda: ["text"])
    output_capabilities: list[str] = Field(default_factory=lambda: ["text"])
    tools: bool = True
    context_limit: int = 128_000
    output_limit: int = 8_192

    @property
    def fq_id(self) -> str:
        return f"{self.provider_id}/{self.id}"

    def supports_lane(self, lane: Lane) -> bool:
        caps = {c.lower() for c in self.input_capabilities}
        if lane == Lane.VISION:
            return "image" in caps
        if lane == Lane.MULTIMODAL:
            return "audio" in caps or "video" in caps
        return "text" in caps


def _is_zero_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == 0 or value == 0.0


def _tier_is_zero_cost(tier: Any) -> bool:
    if not isinstance(tier, Mapping):
        return False
    if "input" not in tier or "output" not in tier:
        return False
    if not (_is_zero_number(tier["input"]) and _is_zero_number(tier["output"])):
        return False

    cache = tier.get("cache")
    if isinstance(cache, Mapping):
        for cache_key in ("read", "write"):
            if cache_key in cache and not _is_zero_number(cache[cache_key]):
                return False
    return True


def is_strictly_zero_cost(cost: Any) -> bool:
    """Verify every pricing tier in `cost` (OpenCode 2.2.6 list or legacy dict) is strictly $0."""
    if isinstance(cost, list):
        return len(cost) > 0 and all(_tier_is_zero_cost(tier) for tier in cost)
    if isinstance(cost, Mapping):
        return _tier_is_zero_cost(cost)
    return False


def filter_free_models(
    raw_models: Iterable[Mapping[str, Any]],
    *,
    allow_google_free: bool = False,
    allow_paid_models: bool = False,
) -> list[OpenCodeModelInfo]:
    """Filter raw `/api/model` entries to Koda's permitted zero-cost routing pool."""
    allowed_providers = {"opencode"}
    if allow_google_free:
        allowed_providers.add("google")

    vetted: list[OpenCodeModelInfo] = []
    for raw in raw_models:
        if not isinstance(raw, Mapping):
            continue
        model_id = str(raw.get("id", "")).strip()
        provider_id = str(raw.get("providerID", raw.get("provider_id", ""))).strip()
        if not model_id or provider_id not in allowed_providers:
            continue

        if not allow_paid_models and not is_strictly_zero_cost(raw.get("cost")):
            continue

        caps_raw = raw.get("capabilities")
        caps = caps_raw if isinstance(caps_raw, Mapping) else {}
        input_caps = [str(x).lower() for x in caps.get("input", ["text"])]
        output_caps = [str(x).lower() for x in caps.get("output", ["text"])]
        limit_raw = raw.get("limit")
        limits = limit_raw if isinstance(limit_raw, Mapping) else {}

        vetted.append(
            OpenCodeModelInfo(
                id=model_id,
                provider_id=provider_id,
                name=str(raw.get("name", model_id)),
                input_capabilities=input_caps or ["text"],
                output_capabilities=output_caps or ["text"],
                tools=bool(caps.get("tools", True)),
                context_limit=int(limits.get("context", 128_000) or 128_000),
                output_limit=int(limits.get("output", 8_192) or 8_192),
            )
        )
    return vetted


def rank_models_for_lane(
    pool: Iterable[OpenCodeModelInfo],
    lane: Lane,
    *,
    telemetry_scores: Mapping[str, tuple[int, float]] | None = None,
) -> list[OpenCodeModelInfo]:
    """
    Order compatible free models for a given lane.

    `telemetry_scores` optionally maps `model_id -> (health_rank, ewma_latency_ms)` where lower
    `health_rank` is healthier (0=HEALTHY, 1=HALF_OPEN, 2=SOFT_SHIFTED).
    """
    eligible = [m for m in pool if m.supports_lane(lane)]
    pref_order = {model_id: idx for idx, model_id in enumerate(LANE_PREFERENCES[lane])}

    def sort_key(model: OpenCodeModelInfo) -> tuple[int, int, int, float, str]:
        health_rank, ewma_ms = (0, 0.0)
        if telemetry_scores and model.id in telemetry_scores:
            health_rank, ewma_ms = telemetry_scores[model.id]
        provider_rank = 0 if model.provider_id == "opencode" else 1
        pref_rank = pref_order.get(model.id, len(pref_order) + 50)
        return (health_rank, provider_rank, pref_rank, ewma_ms, model.id)

    return sorted(eligible, key=sort_key)


def classify_lane_for_request(
    prompt: str,
    *,
    has_image: bool = False,
    has_audio_or_video: bool = False,
    context_chars: int = 0,
) -> Lane:
    """Infer optimal free-model lane from modalities and workload complexity."""
    if has_audio_or_video:
        return Lane.MULTIMODAL
    if has_image:
        return Lane.VISION
    lowered = prompt.lower()
    if context_chars >= 18_000 or len(prompt) >= 6_000 or any(kw in lowered for kw in _DEEP_KEYWORDS):
        return Lane.DEEP_1M
    return Lane.FAST
