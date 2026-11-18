"""Tes SlidingWindowStreamer.

Memakai AudioRingBuffer, VADProcessor, dan Preprocessor ASLI. Yang palsu hanya:
  - prob_fn VAD (berbasis energi, bukan Silero)  -> deterministik
  - engine ASR (teks terjadwal)                  -> tanpa model Whisper
Jalankan dari folder backend/:  python -m pytest tests/test_sliding_window.py -v
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import numpy as np

from app.asr_local.engine import TranscriptionResult
from app.asr_local.streaming_policy import StreamingPolicy
from app.audio.preprocessor import Preprocessor
from app.audio.sliding_window import SlidingWindowStreamer
from app.audio.stream_buffer import AudioRingBuffer
from app.audio.vad_processor import VADProcessor

SR = 16_000


def energy_prob(chunk_f32: np.ndarray) -> float:
    """VAD palsu: RMS besar = bicara."""
    return 0.9 if float(np.sqrt(np.mean(chunk_f32**2))) > 0.05 else 0.0


def feed(buf: AudioRingBuffer, sec: float, speech: bool) -> None:
    n = int(sec * SR)
    if speech:
        t = np.arange(n) / SR
        samples = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    else:
        samples = np.zeros(n, dtype=np.int16)
    buf.write(samples)


class FakeEngine:
    """Mengembalikan teks terjadwal, satu per panggilan; memeriksa format input."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0

    def transcribe(self, audio, **kwargs) -> TranscriptionResult:
        assert audio.dtype == np.float32 and audio.ndim == 1
        self.calls += 1
        text = self.texts.pop(0) if self.texts else ""
        dur = len(audio) / SR
        return TranscriptionResult(
            text=text, segments=(), language="id", language_probability=0.9,
            audio_duration_sec=dur, processing_time_sec=0.1, latency_ms=100.0,
            rtf=0.1 / dur if dur else 0.0, topic="general", initial_prompt="",
            model_size="fake",
        )


def make_streamer(texts: list[str]):
    cfg = SimpleNamespace(
        audio_sample_rate=SR,
        streaming_window_seconds=8.0,
        streaming_silence_final_seconds=1.0,
    )
    buf = AudioRingBuffer()
    vad = VADProcessor(buf, energy_prob)
    eng = FakeEngine(texts)
    streamer = SlidingWindowStreamer(
        buffer=buf, vad=vad, preprocessor=Preprocessor(), engine=eng,
        policy=StreamingPolicy(cfg), step_seconds=0.6,
    )
    return streamer, buf, eng


def test_hening_tidak_memanggil_asr():
    streamer, buf, eng = make_streamer(["seharusnya tidak dipakai"])
    feed(buf, 1.0, speech=False)
    assert asyncio.run(streamer.step()) is None
    assert eng.calls == 0


def test_bicara_menghasilkan_partial_lalu_final_setelah_hening():
    streamer, buf, eng = make_streamer(
        ["halo kita", "halo kita belajar pointer", "halo kita belajar pointer"]
    )

    async def scenario():
        feed(buf, 0.5, speech=False)
        assert await streamer.step() is None

        feed(buf, 1.0, speech=True)
        r1 = await streamer.step()
        assert r1 is not None and r1.update.partial_text == "halo kita"
        assert r1.update.final_text == ""

        feed(buf, 0.6, speech=True)
        r2 = await streamer.step()
        assert r2.update.partial_text == "halo kita belajar pointer"

        feed(buf, 1.5, speech=False)  # hening 1,5 s > batas 1,0 s
        r3 = await streamer.step()
        assert r3.update.final_text == "halo kita belajar pointer"
        assert r3.update.partial_text == ""

        calls_before = eng.calls
        feed(buf, 1.0, speech=False)
        assert await streamer.step() is None  # utterance sudah tertutup
        assert eng.calls == calls_before

    asyncio.run(scenario())


def test_finish_memfinalkan_sisa_partial():
    streamer, buf, eng = make_streamer(["materi linked list", "materi linked list"])

    async def scenario():
        feed(buf, 0.5, speech=False)
        feed(buf, 1.0, speech=True)
        r1 = await streamer.step()
        assert r1.update.partial_text == "materi linked list"
        feed(buf, 0.6, speech=True)
        last = await streamer.finish()
        assert last.update.final_text == "materi linked list"

    asyncio.run(scenario())