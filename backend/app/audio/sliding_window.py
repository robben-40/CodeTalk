"""Sliding Window Streamer: jembatan antara audio (Orang 2) dan ASR (Orang 1).

Letak di pipeline PRD:

    Mic -> [Ring Buffer + VAD] -> [Sliding Window Streamer] -> Engine -> StreamingPolicy -> UI
                                   ^^^^^^^^^^^^^^^^^^^^^^^^
                                   file ini

Tugas utama (dipanggil tiap ~0,5-0,8 detik lewat `step()`):
1. Tanya VAD: ada suara atau hening? (state "utterance" terbuka/tertutup)
2. Kalau sedang hening dan tidak ada yang tertunda -> JANGAN panggil ASR.
3. Kalau perlu, ambil jendela audio dari ring buffer, bersihkan (preprocessor),
   jalankan engine di thread terpisah, lalu serahkan hasilnya ke StreamingPolicy.
4. Kembalikan StepResult (isinya StreamingUpdate + info tambahan untuk telemetry).

Satu instance streamer = satu sesi WebSocket. Engine boleh dipakai bersama
(singleton), tapi buffer, VAD, preprocessor, dan policy harus per sesi.

Disesuaikan dengan API asli:
  - AudioRingBuffer.total_samples / .read(start, end)  -> int16
  - VADProcessor.process_available() / .flush()        -> list[VADEvent]
  - VADEvent.kind: "speech_start" | "speech_end"
  - Preprocessor.__call__(audio)                       -> float32 (menerima int16)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.asr_local.engine import LocalASREngine, TranscriptionResult
from app.asr_local.streaming_policy import StreamingPolicy, StreamingUpdate
from app.audio.preprocessor import Preprocessor
from app.audio.stream_buffer import AudioRingBuffer
from app.audio.vad_processor import VADEvent, VADProcessor

logger = logging.getLogger(__name__)

SPEECH_START = "speech_start"
SPEECH_END = "speech_end"


@dataclass(frozen=True, slots=True)
class StepResult:
    """Hasil satu langkah streamer: update dari policy + info untuk telemetry."""

    update: StreamingUpdate
    window_start_sec: float
    window_end_sec: float
    step_wall_ms: float  # total waktu langkah ini (baca buffer + preprocess + ASR)
    in_speech: bool
    silence_sec: float

    def to_dict(self) -> dict[str, Any]:
        payload = self.update.to_dict()
        payload.update(
            {
                "window_end_sec": round(self.window_end_sec, 3),
                "step_wall_ms": round(self.step_wall_ms, 2),
                "in_speech": self.in_speech,
                "silence_sec": round(self.silence_sec, 3),
            }
        )
        return payload


class SlidingWindowStreamer:
    """Mengatur kapan dan audio mana yang dikirim ke ASR."""

    def __init__(
        self,
        *,
        buffer: AudioRingBuffer,
        vad: VADProcessor,
        preprocessor: Preprocessor,
        engine: LocalASREngine,
        policy: StreamingPolicy,
        step_seconds: float = 0.6,
        min_window_seconds: float = 0.5,
        topic: str | None = None,
        extra_terms: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._buffer = buffer
        self._vad = vad
        self._pre = preprocessor
        self._engine = engine
        self._policy = policy
        self._sr = buffer.sample_rate
        self.step_seconds = step_seconds
        # Jangan inferensi kalau audio baru kurang dari separuh step (percuma, hasilnya sama).
        self._min_new_samples = int(step_seconds * self._sr * 0.5)
        self._min_window_samples = int(min_window_seconds * self._sr)
        self._topic = topic
        self._extra_terms = extra_terms

        # State sesi
        self._utterance_open = False  # True dari "speech_start" sampai finalisasi karena hening
        self._in_speech = False  # True kalau VAD saat ini bilang "sedang bicara"
        self._last_speech_end_sample: int | None = None
        self._last_infer_total = 0  # total sampel saat inferensi terakhir

    # ------------------------------------------------------------------
    # Logika inti
    # ------------------------------------------------------------------
    def _handle_vad_events(self, events: list[VADEvent]) -> None:
        for ev in events:
            if ev.kind == SPEECH_START:
                self._utterance_open = True
                self._in_speech = True
                self._last_speech_end_sample = None
            elif ev.kind == SPEECH_END:
                self._in_speech = False
                self._last_speech_end_sample = int(ev.sample_index)

    def _silence_sec(self, total_samples: int) -> float:
        if self._in_speech or self._last_speech_end_sample is None:
            return 0.0
        return max(0.0, (total_samples - self._last_speech_end_sample) / float(self._sr))

    def _read_and_transcribe(self, start: int, end: int) -> TranscriptionResult:
        """Bagian BERAT & blocking: dijalankan di thread terpisah (bukan di event loop)."""
        raw = self._buffer.read(start, end)  # int16, salinan aman
        audio = self._pre(raw)  # float32 (-1..1), sudah dibersihkan
        return self._engine.transcribe(
            audio,
            topic=self._topic,
            extra_terms=self._extra_terms,
            sample_rate=self._sr,
        )

    async def _infer(self, total: int, *, force_final: bool) -> StepResult | None:
        t0 = time.perf_counter()
        start, end = self._policy.get_window_samples(total, self._sr)
        if end - start < self._min_window_samples:
            return None

        # to_thread: ASR memakan CPU. Kalau dijalankan langsung di sini, seluruh
        # server (termasuk penerimaan audio dari mic) membeku selama inferensi.
        result = await asyncio.to_thread(self._read_and_transcribe, start, end)

        silence = self._silence_sec(total)
        update = self._policy.process_transcription(
            result,
            window_start_sec=start / float(self._sr),
            silence_duration_sec=silence,
            force_final=force_final,
        )
        self._last_infer_total = total

        silence_final = (not self._in_speech) and silence >= self._policy.silence_final_seconds
        if force_final or silence_final:
            # Kalimat sudah difinalkan oleh policy -> tutup utterance, berhenti inferensi
            # sampai VAD mendeteksi suara baru.
            self._utterance_open = False
            self._last_speech_end_sample = None

        return StepResult(
            update=update,
            window_start_sec=start / float(self._sr),
            window_end_sec=end / float(self._sr),
            step_wall_ms=(time.perf_counter() - t0) * 1000.0,
            in_speech=self._in_speech,
            silence_sec=silence,
        )

    async def step(self) -> StepResult | None:
        """Satu langkah streaming. Panggil berulang tiap `step_seconds`.

        Return None kalau memang tidak ada yang perlu dikirim ke UI
        (hening, atau belum ada audio baru yang cukup).
        """
        total = self._buffer.total_samples
        self._handle_vad_events(self._vad.process_available())

        if not self._utterance_open:
            return None  # hening & tidak ada yang tertunda: hemat CPU, cegah halusinasi Whisper
        if total - self._last_infer_total < self._min_new_samples:
            return None
        return await self._infer(total, force_final=False)

    async def finish(self) -> StepResult | StreamingUpdate:
        """Dipanggil saat pengguna menekan Stop / WebSocket ditutup: finalkan sisa teks."""
        total = self._buffer.total_samples
        self._handle_vad_events(self._vad.process_available())
        self._handle_vad_events(self._vad.flush())  # tutup segmen suara yang masih terbuka

        if self._utterance_open:
            result = await self._infer(total, force_final=True)
            if result is not None:
                return result
            self._utterance_open = False
        return self._policy.flush()