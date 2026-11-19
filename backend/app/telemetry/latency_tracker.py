"""latency_tracker.py (Orang 2): mencatat latency & RTF tiap langkah streaming.

Tiga ukuran yang dicatat per langkah (jangan dicampur saat menulis laporan):

  asr_latency_ms : waktu inferensi engine untuk satu jendela (dari engine Orang 1).
  rtf            : asr_latency / durasi jendela audio. Syarat PRD: < 1,0.
  server_e2e_ms  : selisih waktu antara "potongan audio TERBARU di jendela itu tiba
                   di server" dan "hasilnya selesai diproses". Ini pendekatan terbaik
                   di sisi server untuk target latency 1,0-1,5 s di PRD.
                   BELUM termasuk: buffering di browser, jaringan localhost, dan render UI.
                   Jadi latency yang dirasakan pengguna sedikit lebih besar.

Plus `overrun`: True jika satu langkah memakan waktu lebih lama dari step_seconds.
Jika sering True, UI akan tertinggal (RTF efektif terlalu tinggi).
"""

from __future__ import annotations

import bisect
import csv
import math
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class StepRecord:
    t_session_sec: float  # detik sejak sesi dimulai (waktu dinding)
    window_start_sec: float
    window_end_sec: float
    asr_latency_ms: float
    rtf: float
    step_wall_ms: float  # baca buffer + preprocess + ASR
    server_e2e_ms: float | None
    overrun: bool
    in_speech: bool
    has_final: bool


def _stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:  # nearest-rank
        return s[min(n - 1, max(0, math.ceil(p * n) - 1))]

    return {
        "mean": round(sum(s) / n, 3),
        "p50": round(pct(0.5), 3),
        "p95": round(pct(0.95), 3),
        "max": round(s[-1], 3),
    }


class LatencyTracker:
    _MAX_ARRIVALS = 8192

    def __init__(self, sample_rate: int = 16_000, step_seconds: float = 0.6) -> None:
        self._sr = sample_rate
        self._step_ms = step_seconds * 1000.0
        self._t0 = time.monotonic()
        self._arr_totals: list[int] = []  # total sampel kumulatif setelah tiap frame
        self._arr_times: list[float] = []  # waktu tiba frame (monotonic)
        self.records: list[StepRecord] = []

    def mark_audio(self, total_samples: int) -> None:
        """Panggil tiap kali frame audio selesai ditulis ke ring buffer."""
        self._arr_totals.append(total_samples)
        self._arr_times.append(time.monotonic())
        if len(self._arr_totals) > 2 * self._MAX_ARRIVALS:
            del self._arr_totals[: self._MAX_ARRIVALS]
            del self._arr_times[: self._MAX_ARRIVALS]

    def _arrival_time(self, sample_index: int) -> float | None:
        i = bisect.bisect_left(self._arr_totals, sample_index)
        if i >= len(self._arr_totals):
            return None
        return self._arr_times[i]

    def record(self, result: Any) -> StepRecord:
        """Catat satu StepResult (dari SlidingWindowStreamer.step)."""
        now = time.monotonic()
        arrival = self._arrival_time(round(result.window_end_sec * self._sr))
        rec = StepRecord(
            t_session_sec=now - self._t0,
            window_start_sec=result.window_start_sec,
            window_end_sec=result.window_end_sec,
            asr_latency_ms=result.update.latency_ms,
            rtf=result.update.rtf,
            step_wall_ms=result.step_wall_ms,
            server_e2e_ms=None if arrival is None else (now - arrival) * 1000.0,
            overrun=result.step_wall_ms > self._step_ms,
            in_speech=result.in_speech,
            has_final=bool(result.update.final_text),
        )
        self.records.append(rec)
        return rec

    def summary(self) -> dict[str, Any]:
        r = self.records
        return {
            "steps": len(r),
            "overruns": sum(1 for x in r if x.overrun),
            "asr_latency_ms": _stats([x.asr_latency_ms for x in r]),
            "rtf": _stats([x.rtf for x in r]),
            "step_wall_ms": _stats([x.step_wall_ms for x in r]),
            "server_e2e_ms": _stats([x.server_e2e_ms for x in r if x.server_e2e_ms is not None]),
        }

    def write_csv(self, path: Path) -> None:
        names = [f.name for f in fields(StepRecord)]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=names)
            writer.writeheader()
            for rec in self.records:
                row = asdict(rec)
                writer.writerow(
                    {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
                )