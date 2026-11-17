"""Wrapper lokal `faster-whisper` untuk inferensi ASR real-time CodeTalk.

Menggunakan konfigurasi dari `app.config` dan injeksi `initial_prompt`
istilah Computer Science dari `app.asr_local.cs_prompts` untuk mendukung
code-switching Bahasa Indonesia - Inggris.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from app.asr_local.cs_prompts import get_initial_prompt, resolve_topic
from app.config import Settings, get_settings

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SegmentResult:
    """Satu segmen hasil transkripsi dari faster-whisper."""

    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """Hasil transkripsi satu chunk audio beserta metrik latency dan RTF."""

    text: str
    segments: tuple[SegmentResult, ...]
    language: str
    language_probability: float
    audio_duration_sec: float
    processing_time_sec: float
    latency_ms: float
    rtf: float
    topic: str
    initial_prompt: str
    model_size: str

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def to_dict(self) -> dict[str, Any]:
        """Konversi hasil ke dictionary siap-JSON untuk telemetry/API."""
        return {
            "text": self.text,
            "language": self.language,
            "language_probability": round(self.language_probability, 4),
            "audio_duration_sec": round(self.audio_duration_sec, 4),
            "processing_time_sec": round(self.processing_time_sec, 4),
            "latency_ms": round(self.latency_ms, 2),
            "rtf": round(self.rtf, 4),
            "topic": self.topic,
            "model_size": self.model_size,
            "segments": [
                {
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text,
                    "avg_logprob": seg.avg_logprob,
                    "no_speech_prob": seg.no_speech_prob,
                }
                for seg in self.segments
            ],
        }


def prepare_audio_chunk(audio: np.ndarray | bytes) -> np.ndarray:
    """Normalisasi input audio (bytes Int16 PCM atau ndarray) menjadi 1D float32 [-1.0, 1.0]."""
    if isinstance(audio, (bytes, bytearray, memoryview)):
        raw = bytes(audio)
        usable = len(raw) - (len(raw) % 2)
        if usable == 0:
            return np.zeros(0, dtype=np.float32)
        pcm = np.frombuffer(raw[:usable], dtype="<i2")
        return pcm.astype(np.float32) / 32768.0

    arr = np.asarray(audio)
    if arr.size == 0:
        return np.zeros(0, dtype=np.float32)

    # Jika multi-channel, ratakan ke mono 1D.
    if arr.ndim > 1:
        if arr.shape[0] <= 2 and arr.shape[0] < arr.shape[1]:
            arr = arr.mean(axis=0)
        else:
            arr = arr.mean(axis=-1)
    arr = np.reshape(arr, (-1,))

    if np.issubdtype(arr.dtype, np.integer):
        if arr.dtype == np.int16:
            scale = 32768.0
        elif arr.dtype == np.int32:
            scale = 2147483648.0
        else:
            info = np.iinfo(arr.dtype)
            scale = float(max(abs(info.min), info.max))
        float_arr = arr.astype(np.float32) / scale
    else:
        float_arr = np.ascontiguousarray(arr, dtype=np.float32)

    return np.clip(float_arr, -1.0, 1.0)


class LocalASREngine:
    """Wrapper thread-safe untuk model `faster-whisper` lokal."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model: WhisperModel | None = None
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._load_time_sec: float | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_time_sec(self) -> float | None:
        return self._load_time_sec

    def load(self) -> WhisperModel:
        """Muat model `faster-whisper` ke memori secara thread-safe (idempoten)."""
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is not None:
                return self._model

            from faster_whisper import WhisperModel

            model_dir = self.settings.asr_model_dir
            model_dir.mkdir(parents=True, exist_ok=True)

            t0 = time.perf_counter()
            logger.info(
                "Memuat model faster-whisper '%s' (device=%s, compute_type=%s, dir=%s)",
                self.settings.asr_model_size,
                self.settings.asr_device,
                self.settings.asr_compute_type,
                model_dir,
            )
            self._model = WhisperModel(
                model_size_or_path=self.settings.asr_model_size,
                device=self.settings.asr_device,
                compute_type=self.settings.asr_compute_type,
                cpu_threads=self.settings.asr_cpu_threads,
                num_workers=self.settings.asr_num_workers,
                download_root=str(model_dir),
            )
            self._load_time_sec = time.perf_counter() - t0
            logger.info(
                "Model faster-whisper '%s' siap dalam %.2f detik.",
                self.settings.asr_model_size,
                self._load_time_sec,
            )
            return self._model

    def unload(self) -> None:
        """Lepas referensi model dari memori."""
        with self._load_lock:
            self._model = None
            self._load_time_sec = None

    def transcribe(
        self,
        audio: np.ndarray | bytes,
        *,
        topic: str | None = None,
        extra_terms: list[str] | tuple[str, ...] | None = None,
        initial_prompt: str | None = None,
        language: str | None = None,
        beam_size: int | None = None,
        vad_filter: bool | None = None,
        word_timestamps: bool = False,
        sample_rate: int | None = None,
    ) -> TranscriptionResult:
        """Transkripsi satu chunk audio 16kHz mono dan hitung latency + RTF.

        Args:
            audio: Array numpy (int16/float32) atau bytes Int16 PCM 16kHz mono.
            topic: Topik kuliah CS untuk `cs_prompts.py` (default dari config).
            extra_terms: Daftar istilah CS tambahan dari pengguna.
            initial_prompt: Override manual string `initial_prompt` (opsional).
            language: Kode bahasa Whisper (default `'id'` dari config).
            beam_size: Beam size decoding (default dari config).
            vad_filter: Aktifkan filter VAD internal faster-whisper (default dari config).
            word_timestamps: Sertakan timestamp level kata pada segmen internal.
            sample_rate: Sample rate audio input (default `16000` dari config).
        """
        sr = sample_rate or self.settings.audio_sample_rate
        if sr <= 0:
            raise ValueError(f"sample_rate harus > 0, diterima: {sr}")

        audio_f32 = prepare_audio_chunk(audio)
        audio_duration_sec = len(audio_f32) / float(sr)

        resolved_topic = resolve_topic(topic or self.settings.asr_default_topic)
        prompt = (
            initial_prompt.strip()
            if initial_prompt is not None
            else get_initial_prompt(topic=resolved_topic, extra_terms=extra_terms)
        )
        lang = (language or self.settings.asr_language).strip() or "id"

        if audio_f32.size == 0 or audio_duration_sec <= 0.0:
            return TranscriptionResult(
                text="",
                segments=(),
                language=lang,
                language_probability=0.0,
                audio_duration_sec=0.0,
                processing_time_sec=0.0,
                latency_ms=0.0,
                rtf=0.0,
                topic=resolved_topic,
                initial_prompt=prompt,
                model_size=self.settings.asr_model_size,
            )

        model = self.load()
        effective_beam = beam_size if beam_size is not None else self.settings.asr_beam_size
        effective_vad = vad_filter if vad_filter is not None else self.settings.asr_vad_filter

        # faster-whisper mengeksekusi inferensi secara lazy saat generator segmen diiterasi,
        # sehingga pengukuran waktu wajib mencakup iterasi seluruh segmen.
        with self._infer_lock:
            t0 = time.perf_counter()
            segments_iter, info = model.transcribe(
                audio_f32,
                language=lang,
                beam_size=effective_beam,
                initial_prompt=prompt or None,
                condition_on_previous_text=self.settings.asr_condition_on_previous_text,
                vad_filter=effective_vad,
                word_timestamps=word_timestamps,
            )
            collected_segments: list[SegmentResult] = []
            text_parts: list[str] = []
            for seg in segments_iter:
                seg_text = seg.text.strip()
                if seg_text:
                    text_parts.append(seg_text)
                    collected_segments.append(
                        SegmentResult(
                            start=float(seg.start),
                            end=float(seg.end),
                            text=seg_text,
                            avg_logprob=getattr(seg, "avg_logprob", None),
                            no_speech_prob=getattr(seg, "no_speech_prob", None),
                        )
                    )
            processing_time_sec = time.perf_counter() - t0

        latency_ms = processing_time_sec * 1000.0
        rtf = processing_time_sec / audio_duration_sec if audio_duration_sec > 0 else 0.0
        full_text = " ".join(text_parts).strip()

        return TranscriptionResult(
            text=full_text,
            segments=tuple(collected_segments),
            language=getattr(info, "language", lang) or lang,
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            audio_duration_sec=audio_duration_sec,
            processing_time_sec=processing_time_sec,
            latency_ms=latency_ms,
            rtf=rtf,
            topic=resolved_topic,
            initial_prompt=prompt,
            model_size=self.settings.asr_model_size,
        )


_default_engine_lock = threading.Lock()
_default_engine: LocalASREngine | None = None


def get_asr_engine(settings: Settings | None = None) -> LocalASREngine:
    """Kembalikan instance `LocalASREngine` tunggal untuk dipakai bersama di backend."""
    global _default_engine
    if _default_engine is not None:
        return _default_engine
    with _default_engine_lock:
        if _default_engine is None:
            _default_engine = LocalASREngine(settings=settings)
        return _default_engine
