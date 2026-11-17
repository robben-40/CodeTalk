"""Kebijakan pemisahan partial vs final transcript pada sliding-window streaming ASR.

Menggabungkan:
1. Pergeseran batas awal jendela audio (`committed_audio_sec`) agar segmen yang sudah
   final tidak diproses ulang terus-menerus.
2. Penghapusan overlap kata (overlap deduplication) terhadap akhir transkrip final
   sebelumnya agar tidak muncul teks duplikat akibat potongan jendela audio.
3. LocalAgreement (kesepakatan prefix antar langkah berurutan), deteksi akhir kalimat,
   dan finalisasi berbasis jeda hening (VAD silence) / `flush()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.asr_local.engine import TranscriptionResult
from app.config import Settings, get_settings

_EDGE_PUNCT_RE = re.compile(r"^[^\w]+|[^\w]+$")
_SENTENCE_END_CHARS = (".", "?", "!")


def _normalize_token(token: str) -> str:
    """Normalisasi token kata untuk pencocokan overlap & agreement."""
    return _EDGE_PUNCT_RE.sub("", token).lower()


def _tokenize(text: str) -> list[str]:
    return [tok for tok in text.strip().split() if tok]


@dataclass(frozen=True, slots=True)
class StreamingUpdate:
    """Keluaran satu langkah evaluasi `StreamingPolicy` untuk dikirim via WebSocket."""

    final_text: str
    partial_text: str
    committed_transcript: str
    window_start_sec: float
    committed_audio_sec: float
    latency_ms: float
    rtf: float

    @property
    def is_finalized(self) -> bool:
        return bool(self.final_text)

    def to_dict(self) -> dict[str, Any]:
        """Konversi ke payload dictionary siap-JSON untuk client UI."""
        return {
            "final_text": self.final_text,
            "partial_text": self.partial_text,
            "committed_transcript": self.committed_transcript,
            "is_finalized": self.is_finalized,
            "window_start_sec": round(self.window_start_sec, 3),
            "committed_audio_sec": round(self.committed_audio_sec, 3),
            "latency_ms": round(self.latency_ms, 2),
            "rtf": round(self.rtf, 4),
        }


class StreamingPolicy:
    """Mengelola transisi teks `partial` -> `final` tanpa duplikasi pada sliding window."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        window_seconds: float | None = None,
        silence_final_seconds: float | None = None,
        tail_stability_margin_sec: float = 0.8,
        max_partial_words: int = 14,
        min_tail_words: int = 2,
    ) -> None:
        cfg = settings or get_settings()
        self.sample_rate: int = cfg.audio_sample_rate
        self.window_seconds: float = window_seconds or cfg.streaming_window_seconds
        self.silence_final_seconds: float = (
            silence_final_seconds
            if silence_final_seconds is not None
            else cfg.streaming_silence_final_seconds
        )
        self.tail_stability_margin_sec: float = max(0.0, tail_stability_margin_sec)
        self.max_partial_words: int = max(4, max_partial_words)
        self.min_tail_words: int = max(1, min_tail_words)

        self._committed_words: list[str] = []
        self._committed_audio_sec: float = 0.0
        self._prev_hypothesis_words: list[str] = []
        self._last_partial_words: list[str] = []
        self._last_latency_ms: float = 0.0
        self._last_rtf: float = 0.0

    @property
    def committed_audio_sec(self) -> float:
        return self._committed_audio_sec

    @property
    def committed_transcript(self) -> str:
        return " ".join(self._committed_words)

    @property
    def partial_transcript(self) -> str:
        return " ".join(self._last_partial_words)

    def reset(self) -> None:
        """Reset seluruh state sesi transkripsi."""
        self._committed_words.clear()
        self._committed_audio_sec = 0.0
        self._prev_hypothesis_words.clear()
        self._last_partial_words.clear()
        self._last_latency_ms = 0.0
        self._last_rtf = 0.0

    def get_window_seconds(self, latest_audio_sec: float) -> tuple[float, float]:
        """Hitung rentang `[start_sec, end_sec]` jendela audio berikutnya."""
        end_sec = max(0.0, latest_audio_sec)
        start_sec = max(self._committed_audio_sec, end_sec - self.window_seconds)
        if start_sec > end_sec:
            start_sec = end_sec
        return start_sec, end_sec

    def get_window_samples(
        self, total_samples: int, sample_rate: int | None = None
    ) -> tuple[int, int]:
        """Hitung rentang `[start_sample, end_sample)` untuk `AudioRingBuffer.read`."""
        sr = sample_rate or self.sample_rate
        start_sec, end_sec = self.get_window_seconds(total_samples / float(sr))
        return int(start_sec * sr), int(end_sec * sr)

    def _strip_committed_overlap(self, words: list[str]) -> list[str]:
        """Buang prefix `words` yang tumpang-tindih dengan ekor `_committed_words`."""
        if not words or not self._committed_words:
            return words

        max_overlap = min(len(words), len(self._committed_words), 16)
        tail_norm = [_normalize_token(w) for w in self._committed_words[-max_overlap:]]
        head_norm = [_normalize_token(w) for w in words[:max_overlap]]

        for overlap_len in range(max_overlap, 0, -1):
            if tail_norm[-overlap_len:] == head_norm[:overlap_len]:
                return words[overlap_len:]
        return words

    def _longest_common_prefix_len(
        self, prev_words: list[str], curr_words: list[str]
    ) -> int:
        """Hitung panjang prefix kata yang identik (ternormalisasi) antar dua hipotesis."""
        limit = min(len(prev_words), len(curr_words))
        matched = 0
        for idx in range(limit):
            norm_prev = _normalize_token(prev_words[idx])
            norm_curr = _normalize_token(curr_words[idx])
            if not norm_prev or norm_prev != norm_curr:
                break
            matched += 1
        return matched

    def _estimate_commit_end_sec(
        self,
        result: TranscriptionResult,
        window_start_sec: float,
        committed_count: int,
        total_candidate_words: int,
    ) -> float:
        """Perkirakan timestamp absolut akhir kata yang baru difinalkan."""
        if total_candidate_words <= 0 or committed_count <= 0:
            return self._committed_audio_sec

        if committed_count >= total_candidate_words:
            if result.segments:
                return max(
                    self._committed_audio_sec,
                    window_start_sec + result.segments[-1].end,
                )
            return max(
                self._committed_audio_sec,
                window_start_sec + result.audio_duration_sec,
            )

        # Jika ada segmen dengan durasi jelas, interpolasi proporsional sampai kata ke-N.
        span_end = (
            result.segments[-1].end if result.segments else result.audio_duration_sec
        )
        ratio = committed_count / float(total_candidate_words)
        estimated = window_start_sec + (span_end * ratio)
        return max(self._committed_audio_sec, estimated)

    def _commit_words(self, words: list[str], new_committed_audio_sec: float) -> str:
        """Simpan kata baru ke `_committed_words` setelah cek duplikasi ekor."""
        deduped = self._strip_committed_overlap(words)
        self._committed_audio_sec = max(
            self._committed_audio_sec, new_committed_audio_sec
        )
        if not deduped:
            return ""
        self._committed_words.extend(deduped)
        return " ".join(deduped)

    def process_transcription(
        self,
        result: TranscriptionResult,
        *,
        window_start_sec: float = 0.0,
        silence_duration_sec: float = 0.0,
        force_final: bool = False,
    ) -> StreamingUpdate:
        """Proses hasil transkripsi satu sliding window menjadi `final_text` & `partial_text`."""
        self._last_latency_ms = result.latency_ms
        self._last_rtf = result.rtf

        raw_words = _tokenize(result.text)
        candidate_words = self._strip_committed_overlap(raw_words)

        # Kasus 1: hening cukup lama atau flush paksa -> finalkan kandidat / partial tersisa.
        if force_final or silence_duration_sec >= self.silence_final_seconds:
            words_to_commit = candidate_words or self._last_partial_words
            end_sec = (
                window_start_sec + result.audio_duration_sec
                if candidate_words
                else self._committed_audio_sec
            )
            final_text = self._commit_words(words_to_commit, end_sec)
            self._prev_hypothesis_words = []
            self._last_partial_words = []
            return StreamingUpdate(
                final_text=final_text,
                partial_text="",
                committed_transcript=self.committed_transcript,
                window_start_sec=self._committed_audio_sec,
                committed_audio_sec=self._committed_audio_sec,
                latency_ms=result.latency_ms,
                rtf=result.rtf,
            )

        if not candidate_words:
            return StreamingUpdate(
                final_text="",
                partial_text=" ".join(self._last_partial_words),
                committed_transcript=self.committed_transcript,
                window_start_sec=window_start_sec,
                committed_audio_sec=self._committed_audio_sec,
                latency_ms=result.latency_ms,
                rtf=result.rtf,
            )

        # Kasus 2: cari prefix yang stabil (LocalAgreement) dan batas kalimat aman.
        lcp_len = self._longest_common_prefix_len(
            self._prev_hypothesis_words, candidate_words
        )
        commit_count = 0

        # Prioritas A: ada tanda akhir kalimat di dalam prefix yang sudah disepakati.
        for idx in range(lcp_len - 1, -1, -1):
            if candidate_words[idx].endswith(_SENTENCE_END_CHARS):
                commit_count = idx + 1
                break

        # Prioritas B: jendela sudah panjang / mendekati kapasitas, finalkan prefix stabil
        # sambil menyisakan beberapa kata ekor (`min_tail_words`) agar transisi halus.
        window_near_full = (
            result.audio_duration_sec
            >= max(1.0, self.window_seconds - self.tail_stability_margin_sec)
        )
        if commit_count == 0 and (
            len(candidate_words) >= self.max_partial_words or window_near_full
        ):
            safe_agreed = min(lcp_len, max(0, len(candidate_words) - self.min_tail_words))
            if safe_agreed > 0:
                commit_count = safe_agreed

        final_text = ""
        if commit_count > 0:
            to_commit = candidate_words[:commit_count]
            remaining = candidate_words[commit_count:]
            new_audio_cursor = self._estimate_commit_end_sec(
                result=result,
                window_start_sec=window_start_sec,
                committed_count=commit_count,
                total_candidate_words=len(candidate_words),
            )
            final_text = self._commit_words(to_commit, new_audio_cursor)
        else:
            remaining = candidate_words

        self._prev_hypothesis_words = list(remaining)
        self._last_partial_words = list(remaining)

        return StreamingUpdate(
            final_text=final_text,
            partial_text=" ".join(remaining),
            committed_transcript=self.committed_transcript,
            window_start_sec=max(window_start_sec, self._committed_audio_sec),
            committed_audio_sec=self._committed_audio_sec,
            latency_ms=result.latency_ms,
            rtf=result.rtf,
        )

    def flush(self) -> StreamingUpdate:
        """Finalkan sisa `partial_text` di akhir sesi rekaman."""
        final_text = self._commit_words(
            self._last_partial_words, self._committed_audio_sec
        )
        self._prev_hypothesis_words = []
        self._last_partial_words = []
        return StreamingUpdate(
            final_text=final_text,
            partial_text="",
            committed_transcript=self.committed_transcript,
            window_start_sec=self._committed_audio_sec,
            committed_audio_sec=self._committed_audio_sec,
            latency_ms=self._last_latency_ms,
            rtf=self._last_rtf,
        )
