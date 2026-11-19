"""session_logger.py (Orang 2): menyimpan satu sesi ke disk untuk laporan (FR08).

Tiap sesi menghasilkan satu folder berisi:
  transcript.txt : transkrip final gabungan (bahan hitung WER)
  latency.csv    : satu baris per langkah streaming (bahan tabel latency/RTF)
  session.json   : konfigurasi sesi + segmen final + ringkasan statistik

Konfigurasi (model, step, window, dll.) ikut disimpan supaya tiap eksperimen
(baseline vs noise vs speed) bisa dilacak kondisinya.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

DEFAULT_LOG_DIR = PROJECT_ROOT / "evaluation" / "results" / "sessions"


class SessionLogger:
    def __init__(
        self,
        session_id: str,
        topic: str,
        meta: dict[str, Any] | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.topic = topic
        self.meta = dict(meta or {})
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_LOG_DIR
        self.started_at = datetime.now()
        self.segments: list[dict[str, Any]] = []

    def add_final(self, text: str, audio_sec: float) -> None:
        self.segments.append({"audio_sec": round(audio_sec, 3), "text": text})

    def save(self, committed_transcript: str, tracker: Any, reason: str) -> Path:
        ended_at = datetime.now()
        folder = self.base_dir / f"{self.started_at:%Y%m%d-%H%M%S}-{self.session_id[:8]}"
        folder.mkdir(parents=True, exist_ok=True)

        (folder / "transcript.txt").write_text(committed_transcript + "\n", encoding="utf-8")
        tracker.write_csv(folder / "latency.csv")

        session = {
            "session_id": self.session_id,
            "topic": self.topic,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "ended_at": ended_at.isoformat(timespec="seconds"),
            "end_reason": reason,
            "config": self.meta,
            "segments": self.segments,
            "summary": tracker.summary(),
        }
        (folder / "session.json").write_text(
            json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return folder