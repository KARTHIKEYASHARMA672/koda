from __future__ import annotations

import asyncio
import math
import struct
import time
from pathlib import Path

from fastapi.testclient import TestClient

from koda.config import KodaSettings
from koda.gateway.app import KodaService, create_app
from koda.voice.pipeline import SpeechSynthesizer, VadEndpointTracker, VoicePipeline, compute_rms


def _make_pcm_frame(amplitude: int, samples: int = 480, freq_hz: float = 440.0) -> bytes:
    out = bytearray()
    for i in range(samples):
        val = int(amplitude * math.sin(2.0 * math.pi * freq_hz * (i / 16000.0)))
        out.extend(struct.pack("<h", max(-32768, min(32767, val))))
    return bytes(out)


def test_compute_rms_and_vad_endpoint_segmentation() -> None:
    silence = _make_pcm_frame(0)
    speech = _make_pcm_frame(12000)

    assert compute_rms(silence) == 0.0
    assert compute_rms(speech) > 0.2

    vad = VadEndpointTracker(
        speech_threshold=0.05,
        min_speech_frames=2,
        silence_hangover_frames=3,
        max_frames=20,
    )

    # Leading noise/silence produces nothing
    assert vad.feed(silence) is None
    assert vad.feed(silence) is None

    # Active speech accumulates without early emission
    for _ in range(4):
        assert vad.feed(speech) is None

    # Hangover silence completes utterance cleanly after 3 silent frames
    assert vad.feed(silence) is None
    assert vad.feed(silence) is None
    utterance = vad.feed(silence)

    assert utterance is not None
    # 4 speech frames + 3 silence hangover frames
    assert len(utterance) == 7 * len(speech)


def test_barge_in_cancels_tts_playback_under_150ms() -> None:
    stopped = {"flag": False}

    class SlowAudioBackend:
        async def synthesize(self, text: str, voice: str) -> bytes:
            return b"FAKE_MP3_BYTES"

        async def play(self, audio_bytes: bytes, stop_event: asyncio.Event) -> None:
            while not stop_event.is_set():
                await asyncio.sleep(0.01)
            stopped["flag"] = True

    synth = SpeechSynthesizer(backend=SlowAudioBackend())

    async def run() -> float:
        speak_task = asyncio.create_task(synth.speak("This is a long Jarvis briefing that gets interrupted."))
        await asyncio.sleep(0.03)
        t0 = time.perf_counter()
        synth.barge_in()
        await speak_task
        return (time.perf_counter() - t0) * 1000.0

    cancel_ms = asyncio.run(run())
    assert stopped["flag"] is True
    assert cancel_ms < 150.0


def test_voice_pipeline_roundtrip_and_gateway_endpoints(tmp_path: Path) -> None:
    states: list[str] = []

    class FakeSTT:
        async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
            assert len(pcm_bytes) > 0
            return "What is my status?"

    class FakeSynthBackend:
        async def synthesize(self, text: str, voice: str) -> bytes:
            return text.encode("utf-8")

        async def play(self, audio_bytes: bytes, stop_event: asyncio.Event) -> None:
            await asyncio.sleep(0.01)

    spoken_texts: list[str] = []

    async def fake_reply(transcript: str) -> str:
        spoken_texts.append(transcript)
        return "All zero-cost systems are nominal."

    pipeline = VoicePipeline(
        stt=FakeSTT(),
        synthesizer=SpeechSynthesizer(backend=FakeSynthBackend()),
        on_transcript=fake_reply,
        on_state_change=lambda st: states.append(st),
    )

    async def run_pipe() -> str:
        speech = _make_pcm_frame(12000) * 3
        return await pipeline.process_utterance(speech)

    reply = asyncio.run(run_pipe())
    assert reply == "All zero-cost systems are nominal."
    assert spoken_texts == ["What is my status?"]
    assert states == ["thinking", "speaking", "idle"]

    # Check FastAPI voice endpoints
    class StubOC:
        async def health(self) -> dict:
            return {"version": "2.2.6"}

        async def list_models(self) -> list[dict]:
            return []

        async def close(self) -> None:
            return None

    settings = KodaSettings(_env_file=None, data_dir=tmp_path, allowed_roots_raw=str(tmp_path))
    svc = KodaService(settings=settings, client=StubOC(), managed_opencode=False)  # type: ignore[arg-type]
    app = create_app(svc)

    with TestClient(app) as client:
        vs = client.get("/api/voice/status")
        assert vs.status_code == 200
        assert vs.json()["wake_word"] == "hey_jarvis"

        bi = client.post("/api/voice/barge-in")
        assert bi.status_code == 200
        assert bi.json()["barge_in"] is True
