from __future__ import annotations

from koda.opencode.models import (
    Lane,
    OpenCodeModelInfo,
    classify_lane_for_request,
    filter_free_models,
    rank_models_for_lane,
)


def _raw_model(
    model_id: str,
    *,
    provider_id: str = "opencode",
    cost: object = None,
    input_caps: list[str] | None = None,
    tools: bool = True,
) -> dict:
    if cost is None:
        cost = [{"input": 0, "output": 0, "cache": {"read": 0, "write": 0}}]
    return {
        "id": model_id,
        "providerID": provider_id,
        "name": model_id,
        "cost": cost,
        "capabilities": {
            "tools": tools,
            "input": input_caps if input_caps is not None else ["text"],
            "output": ["text"],
        },
        "limit": {"context": 128000, "output": 8192},
    }


def test_filter_free_models_strictly_rejects_paid_and_malformed_tiers() -> None:
    raw = [
        _raw_model("iceman-free"),
        _raw_model(
            "tiered-paid",
            cost=[
                {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}},
                {"input": 0.5, "output": 1.5, "cache": {"read": 0, "write": 0}},
            ],
        ),
        _raw_model(
            "cache-paid",
            cost=[{"input": 0, "output": 0, "cache": {"read": 0.01, "write": 0}}],
        ),
        _raw_model("empty-cost", cost=[]),
        _raw_model("dict-zero", cost={"input": 0, "output": 0}),
        _raw_model("google-gemma", provider_id="google"),
    ]

    free = filter_free_models(raw, allow_google_free=False, allow_paid_models=False)
    ids = {m.id for m in free}

    assert ids == {"iceman-free", "dict-zero"}


def test_filter_free_models_allows_zero_cost_google_only_when_enabled() -> None:
    raw = [
        _raw_model("iceman-free"),
        _raw_model("gemma-4-31b-it", provider_id="google"),
        _raw_model("gemini-pro-paid", provider_id="google", cost=[{"input": 1.25, "output": 5.0}]),
    ]

    free = filter_free_models(raw, allow_google_free=True, allow_paid_models=False)
    assert [(m.provider_id, m.id) for m in free] == [
        ("opencode", "iceman-free"),
        ("google", "gemma-4-31b-it"),
    ]


def test_lane_ranking_groups_real_226_free_models() -> None:
    raw = [
        _raw_model("iceman-free", input_caps=["text"]),
        _raw_model("nemotron-3.5-lightning-free", input_caps=["text"]),
        _raw_model("nemotron-3.5-super-vl-free", input_caps=["text", "image"]),
        _raw_model("deepseek-v4.1-flash-free", input_caps=["text", "image"]),
        _raw_model("minimax-m3.1-flash-free", input_caps=["text", "image", "video"]),
        _raw_model("mimo-v2.6-flash-free", input_caps=["text", "image", "audio", "video"]),
    ]

    pool = filter_free_models(raw)
    assert all(isinstance(m, OpenCodeModelInfo) for m in pool)

    vision_ids = [m.id for m in rank_models_for_lane(pool, Lane.VISION)]
    assert vision_ids[0] == "nemotron-3.5-super-vl-free"
    assert "deepseek-v4.1-flash-free" in vision_ids
    assert "iceman-free" not in vision_ids

    multimodal_ids = [m.id for m in rank_models_for_lane(pool, Lane.MULTIMODAL)]
    assert multimodal_ids[0] == "mimo-v2.6-flash-free"
    assert "minimax-m3.1-flash-free" in multimodal_ids

    deep_ids = [m.id for m in rank_models_for_lane(pool, Lane.DEEP_1M)]
    assert "nemotron-3.5-lightning-free" in deep_ids
    assert "minimax-m3.1-flash-free" in deep_ids

    fast_ids = [m.id for m in rank_models_for_lane(pool, Lane.FAST)]
    assert fast_ids[0] == "iceman-free"


def test_classify_lane_for_request() -> None:
    assert classify_lane_for_request("what time is it?") == Lane.FAST
    assert classify_lane_for_request("read this error", has_image=True) == Lane.VISION
    assert classify_lane_for_request("transcribe clip", has_audio_or_video=True) == Lane.MULTIMODAL
    assert classify_lane_for_request("analyze architecture", context_chars=24000) == Lane.DEEP_1M
