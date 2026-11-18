"""Tes StreamSession (inti ws_stream.py) tanpa server, tanpa Silero, tanpa Whisper.

WebSocket diganti objek palsu; VAD memakai prob_fn berbasis energi; engine palsu
mengembalikan teks tetap. Jalankan dari folder backend/:
    python -m pytest tests/test_ws_stream.py -v
Catatan: tes ini memakai waktu dinding (~1 detik) karena loop streaming berdetak tiap 0,6 s.
"""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.api import ws_stream
from app.asr_local.engine import TranscriptionResult
from app.telemetry.latency_tracker import LatencyTracker

SR = 16_000
TEXT = "halo kita belajar pointer"


def energy_prob(chunk_f32: np.ndarray) -> float:
    return 0.9 if float(np.sqrt(np.mean(chunk_f32**2))) > 0.05 else 0.0


def pcm(sec: float, speech: bool) -> bytes:
    n = int(sec * SR)
    if speech:
        t = np.arange(n) / SR
        return (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16).tobytes()
    return np.zeros(n, dtype=np.int16).tobytes()


class FakeEngine:
    is_loaded = True

    def transcribe(self, audio, **kwargs) -> TranscriptionResult:
        assert audio.dtype == np.float32 and audio.ndim == 1
        dur = len(audio) / SR
        return TranscriptionResult(
            text=TEXT, segments=(), language="id", language_probability=0.9,
            audio_duration_sec=dur, processing_time_sec=0.05, latency_ms=50.0,
            rtf=0.05 / dur if dur else 0.0, topic="oop", initial_prompt="",
            model_size="fake",
        )


class FakeWebSocket:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []

    async def receive(self) -> dict:
        return await self.incoming.get()

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        pass


async def feed(ws: FakeWebSocket, parts, raw_texts=(), wait_after: float = 0.9) -> None:
    for sec, speech in parts:
        data = pcm(sec, speech)
        for i in range(0, len(data), 3200):  # frame 100 ms
            await ws.incoming.put({"type": "websocket.receive", "bytes": data[i : i + 3200]})
    for raw in raw_texts:
        await ws.incoming.put({"type": "websocket.receive", "text": raw})
    await asyncio.sleep(wait_after)  # beri waktu >= satu langkah (0,6 s)
    await ws.incoming.put({"type": "websocket.receive", "text": json.dumps({"type": "stop"})})


def run_scenario(tmp_path: Path, parts, raw_texts=()) -> list[dict]:
    async def scenario():
        ws = FakeWebSocket()
        session = ws_stream.StreamSession(
            ws, FakeEngine(), energy_prob, topic="oop", extra_terms=None, log_dir=tmp_path
        )
        await asyncio.gather(session.run(), feed(ws, parts, raw_texts))
        return ws.sent

    return asyncio.run(scenario())


def test_sesi_lengkap_dari_audio_sampai_stopped(tmp_path):
    sent = run_scenario(tmp_path, [(0.5, False), (1.5, True), (1.5, False)])

    assert sent[0]["type"] == "ready" and sent[0]["topic"] == "oop"
    assert sent[-1]["type"] == "stopped"

    states = [m["state"] for m in sent if m["type"] == "status"]
    assert states[0] == "listening" and states[-1] == "stopped"

    finals = [m["final_text"] for m in sent if m["type"] == "transcript" and m["final_text"]]
    assert " ".join(finals) == TEXT  # tidak ada teks ganda
    assert sent[-1]["committed_transcript"] == TEXT


def test_log_sesi_tersimpan_di_disk(tmp_path):
    run_scenario(tmp_path, [(0.5, False), (1.5, True), (1.5, False)])

    folder = next(tmp_path.iterdir())
    assert (folder / "transcript.txt").read_text(encoding="utf-8").strip() == TEXT
    info = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert info["topic"] == "oop" and info["end_reason"] == "stop"
    assert info["config"]["streaming_step_seconds"] > 0
    with open(folder / "latency.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 1 and "rtf" in rows[0] and "server_e2e_ms" in rows[0]


def test_pesan_teks_bukan_json_tidak_mematikan_sesi(tmp_path):
    sent = run_scenario(tmp_path, [], raw_texts=["bukan json"])
    assert any(m["type"] == "error" for m in sent)
    assert sent[-1]["type"] == "stopped"


def test_latency_tracker_overrun_dan_ringkasan():
    tr = LatencyTracker(sample_rate=SR, step_seconds=0.6)
    assert tr.summary()["steps"] == 0

    def fake_result(wall_ms: float, end_sec: float):
        update = SimpleNamespace(latency_ms=wall_ms - 10, rtf=0.3, final_text="")
        return SimpleNamespace(
            window_start_sec=0.0, window_end_sec=end_sec, step_wall_ms=wall_ms,
            update=update, in_speech=True,
        )

    tr.mark_audio(SR)  # 1 detik audio sudah tiba
    tr.record(fake_result(400.0, 1.0))   # di bawah 600 ms -> bukan overrun
    tr.record(fake_result(900.0, 1.0))   # di atas 600 ms -> overrun
    s = tr.summary()
    assert s["steps"] == 2 and s["overruns"] == 1
    assert s["server_e2e_ms"] is not None