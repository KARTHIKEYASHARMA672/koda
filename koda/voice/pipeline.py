"""Full-duplex voice pipeline: RMS/VAD framing, faster-whisper STT, edge-tts, and <150ms barge-in."""

from __future__ import annotations

import asyncio
import io
import logging
import math
import tempfile
import wave
from array import array
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


def compute_rms(pcm_int16: bytes) -> float:
    """Compute normalized RMS amplitude (0.0..1.0) from mono 16-bit signed PCM bytes."""
    if len(pcm_int16) < 2:
        return 0.0
    samples = array("h")
    usable = len(pcm_int16) - (len(pcm_int16) % 2)
    samples.frombytes(pcm_int16[:usable])
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return min(1.0, math.sqrt(mean_sq) / 32768.0)


class VadEndpointTracker:
    """Segments continuous PCM frames into completed utterances using energy + hangover."""

    def __init__(
        self,
        *,
        speech_threshold: float = 0.03,
        min_speech_frames: int = 3,
        silence_hangover_frames: int = 12,
        max_frames: int = 400,
    ) -> None:
        self.speech_threshold = speech_threshold
        self.min_speech_frames = min_speech_frames
        self.silence_hangover_frames = silence_hangover_frames
        self.max_frames = max_frames
        self._frames: list[bytes] = []
        self._speech_count = 0
        self._silence_count = 0
        self._active = False

    def reset(self) -> None:
        self._frames.clear()
        self._speech_count = 0
        self._silence_count = 0
        self._active = False

    def feed(self, frame: bytes) -> bytes | None:
        rms = compute_rms(frame)
        if rms >= self.speech_threshold:
            self._frames.append(frame)
            self._speech_count += 1
            self._silence_count = 0
            if self._speech_count >= self.min_speech_frames:
                self._active = True
            if len(self._frames) >= self.max_frames:
                out = b"".join(self._frames)
                self.reset()
                return out
            return None

        if not self._active:
            # Discard brief pre-speech clicks that never reached min_speech_frames.
            self.reset()
            return None

        self._frames.append(frame)
        self._silence_count += 1
        if self._silence_count >= self.silence_hangover_frames or len(self._frames) >= self.max_frames:
            out = b"".join(self._frames)
            self.reset()
            return out
        return None


class STTBackend(Protocol):
    async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str: ...


class TTSBackend(Protocol):
    async def synthesize(self, text: str, voice: str) -> bytes: ...

    async def play(self, audio_bytes: bytes, stop_event: asyncio.Event) -> None: ...


class LocalFasterWhisperSTT:
    """Lazy-loading `faster-whisper` transcriber running off the asyncio event loop."""

    def __init__(self, *, model_name: str = "base.en", device: str = "auto", compute_type: str = "int8") -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model

    async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        if not pcm_bytes:
            return ""

        def _run() -> str:
            model = self._ensure_model()
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_bytes)
            wav_buf.seek(0)
            segments, _info = model.transcribe(wav_buf, beam_size=1, vad_filter=True)
            return " ".join(seg.text.strip() for seg in segments if seg.text).strip()

        return await asyncio.to_thread(_run)


class EdgeTTSAudioBackend:
    """Low-latency natural speech via `edge-tts` + interruptible Windows/sounddevice playback."""

    async def synthesize(self, text: str, voice: str) -> bytes:
        import edge_tts

        comm = edge_tts.Communicate(text, voice=voice)
        buf = io.BytesIO()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buf.write(chunk["data"])
        return buf.getvalue()

    async def play(self, audio_bytes: bytes, stop_event: asyncio.Event) -> None:
        if not audio_bytes or stop_event.is_set():
            return

        # Decode MP3 via torchaudio/temp file only when actually playing audio.
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                tf.write(audio_bytes)
                tmp_path = Path(tf.name)

            def _play_with_winmm() -> None:
                import ctypes

                alias = f"koda_tts_{id(stop_event)}"
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f'open "{tmp_path}" type mpegvideo alias {alias}', None, 0, None)
                winmm.mciSendStringW(f"play {alias}", None, 0, None)
                try:
                    import time

                    buf = ctypes.create_unicode_buffer(64)
                    while not stop_event.is_set():
                        winmm.mciSendStringW(f"status {alias} mode", buf, 64, None)
                        if buf.value.strip().lower() not in {"playing", "seeking"}:
                            break
                        time.sleep(0.02)
                finally:
                    winmm.mciSendStringW(f"stop {alias}", None, 0, None)
                    winmm.mciSendStringW(f"close {alias}", None, 0, None)

            await asyncio.to_thread(_play_with_winmm)
        except Exception as exc:
            logger.debug("TTS audio playback skipped/failed: %s", exc)
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


class SpeechSynthesizer:
    """Thread/async-safe TTS controller supporting instant `< 150 ms` barge-in."""

    def __init__(self, *, backend: TTSBackend | None = None, voice: str = "en-GB-RyanNeural") -> None:
        self.backend: TTSBackend = backend or EdgeTTSAudioBackend()
        self.voice = voice
        self._stop_event = asyncio.Event()
        self.is_speaking = False

    def barge_in(self) -> None:
        """Immediately halt active speech output."""
        self._stop_event.set()
        self.is_speaking = False

    async def speak(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        self._stop_event = asyncio.Event()
        self.is_speaking = True
        try:
            audio = await self.backend.synthesize(cleaned, self.voice)
            if self._stop_event.is_set():
                return
            await self.backend.play(audio, self._stop_event)
        finally:
            self.is_speaking = False


class VoicePipeline:
    """Coordinates wake word / VAD capture, STT transcription, Koda reply, and TTS barge-in."""

    def __init__(
        self,
        *,
        stt: STTBackend | None = None,
        synthesizer: SpeechSynthesizer | None = None,
        on_transcript: Callable[[str], Awaitable[str]] | None = None,
        on_state_change: Callable[[str], Any] | None = None,
        wake_word: str = "hey_jarvis",
        stt_model: str = "base.en",
        tts_voice: str = "en-GB-RyanNeural",
    ) -> None:
        self.wake_word = wake_word
        self.stt: STTBackend = stt or LocalFasterWhisperSTT(model_name=stt_model)
        self.synthesizer = synthesizer or SpeechSynthesizer(voice=tts_voice)
        self.on_transcript = on_transcript
        self.on_state_change = on_state_change
        self.vad = VadEndpointTracker()
        self.listening = False
        self.dictation_mode = False
        self._mic_task: asyncio.Task[None] | None = None

    def _emit_state(self, state: str) -> None:
        if self.on_state_change is not None:
            self.on_state_change(state)

    def barge_in(self) -> None:
        self.synthesizer.barge_in()
        self._emit_state("listening" if self.listening else "idle")

    async def dictate_into_active_window(self, text: str) -> None:
        def _type() -> None:
            import pyautogui

            pyautogui.write(text, interval=0.01)

        await asyncio.to_thread(_type)

    async def process_utterance(self, pcm_bytes: bytes, *, sample_rate: int = 16000) -> str:
        self._emit_state("thinking")
        transcript = (await self.stt.transcribe_pcm(pcm_bytes, sample_rate=sample_rate)).strip()
        if not transcript:
            self._emit_state("idle")
            return ""

        if self.dictation_mode:
            await self.dictate_into_active_window(transcript + " ")
            self._emit_state("idle")
            return transcript

        if self.on_transcript is None:
            self._emit_state("idle")
            return transcript

        reply = (await self.on_transcript(transcript)).strip()
        if reply:
            self._emit_state("speaking")
            await self.synthesizer.speak(reply)
        self._emit_state("idle")
        return reply

    async def start_listening(self) -> dict[str, Any]:
        if self.listening:
            return {"ok": True, "listening": True}
        try:
            import sounddevice as sd
        except Exception as exc:
            return {"ok": False, "error": f"Audio input unavailable: {exc}"}

        self.listening = True
        self._emit_state("listening")

        async def _capture_loop() -> None:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

            def _audio_cb(indata: bytes, _frames: int, _time_info: Any, _status: Any) -> None:
                if not queue.full():
                    loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

            try:
                with sd.RawInputStream(samplerate=16000, blocksize=480, dtype="int16", channels=1, callback=_audio_cb):
                    while self.listening:
                        frame = await queue.get()
                        if self.synthesizer.is_speaking and compute_rms(frame) > 0.08:
                            self.barge_in()
                        utt = self.vad.feed(frame)
                        if utt is not None:
                            await self.process_utterance(utt)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Microphone capture loop stopped: %s", exc)
            finally:
                self.listening = False
                self._emit_state("idle")

        self._mic_task = asyncio.create_task(_capture_loop())
        return {"ok": True, "listening": True}

    async def stop_listening(self) -> dict[str, Any]:
        self.listening = False
        if self._mic_task is not None:
            self._mic_task.cancel()
            try:
                await self._mic_task
            except asyncio.CancelledError:
                pass
            self._mic_task = None
        self._emit_state("idle")
        return {"ok": True, "listening": False}
