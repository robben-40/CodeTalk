"""ws_stream.py (Orang 2): endpoint WebSocket streaming audio -> transkripsi real-time.

KONTRAK DENGAN FRONTEND (usulan, harus dikonfirmasi Orang 3)
-------------------------------------------------------------
URL        : ws://localhost:8000/ws/stream?topic=oop&extra_terms=pointer,heap
             (topic & extra_terms opsional; topic mengikuti kunci/alias di cs_prompts.py)

PENTING: client HARUS menunggu pesan {"type":"ready"} sebelum mengirim frame audio.
         "ready" baru dikirim setelah model ASR & VAD siap (bisa lama di sesi pertama).
         Audio yang dikirim lebih awal tidak dibaca server, antrean penuh, lalu koneksi
         putus dengan "keepalive ping timeout" (kode 1011).

Client -> Server
  * frame BINER : PCM Int16 little-endian, 16 kHz, mono (resampling dilakukan frontend).
                  Ukuran frame bebas (disarankan ~100 ms = 3200 byte).
  * teks JSON   : {"type": "stop"}  -> akhiri sesi dengan rapi (finalkan sisa teks).
                  Menutup koneksi tanpa pesan ini juga dianggap Stop.

Server -> Client (semua JSON, field "type" menentukan jenis)
  {"type":"ready", "session_id", "topic", "sample_rate", "step_seconds", ...}
  {"type":"status", "state":"listening" | "processing" | "stopped"}
  {"type":"transcript", "final_text", "partial_text", "committed_transcript",
        "is_finalized", "latency_ms", "rtf", "step_wall_ms", "server_e2e_ms",
        "in_speech", "silence_sec", "window_start_sec", "window_end_sec", ...}
  {"type":"error", "message"}
  {"type":"stopped", "reason", "committed_transcript", "summary", "log_dir"}

Makna status:  listening  = menunggu / hening
               processing = ada ucapan yang sedang diproses (partial berjalan)
               stopped    = sesi berakhir
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.asr_local.cs_prompts import resolve_topic
from app.asr_local.engine import get_asr_engine
from app.asr_local.streaming_policy import StreamingPolicy, StreamingUpdate
from app.audio.preprocessor import Preprocessor
from app.audio.sliding_window import SlidingWindowStreamer, StepResult
from app.audio.stream_buffer import AudioRingBuffer
from app.audio.vad_processor import VADProcessor, make_silero_prob_fn
from app.config import settings
from app.telemetry.latency_tracker import LatencyTracker
from app.telemetry.session_logger import DEFAULT_LOG_DIR, SessionLogger

logger = logging.getLogger(__name__)

router = APIRouter()
LOG_DIR = DEFAULT_LOG_DIR


class StreamSession:
    """Satu sesi = satu koneksi WebSocket. Semua state sesi (buffer, VAD, policy) milik sendiri."""

    def __init__(
        self,
        websocket: Any,
        engine: Any,
        prob_fn: Any,
        *,
        topic: str,
        extra_terms: list[str] | None,
        log_dir: Path | None = None,
    ) -> None:
        cfg = settings
        self.ws = websocket
        self.topic = topic
        self.sr = cfg.audio_sample_rate
        self.step_seconds = cfg.streaming_step_seconds
        self.session_id = uuid.uuid4().hex

        # Silero punya memori internal antar-chunk: wajib di-reset di awal sesi baru.
        reset = getattr(prob_fn, "reset", None)
        if callable(reset):
            reset()

        self.buffer = AudioRingBuffer(cfg.audio_buffer_max_seconds, self.sr)
        vad = VADProcessor(self.buffer, prob_fn, threshold=cfg.vad_threshold)
        self.streamer = SlidingWindowStreamer(
            buffer=self.buffer,
            vad=vad,
            preprocessor=Preprocessor(self.sr),
            engine=engine,
            policy=StreamingPolicy(cfg),
            step_seconds=self.step_seconds,
            min_window_seconds=cfg.streaming_min_audio_seconds,
            topic=topic,
            extra_terms=extra_terms,
        )
        self.tracker = LatencyTracker(self.sr, self.step_seconds)
        self.logger = SessionLogger(
            self.session_id,
            topic,
            meta={
                "asr_model_size": cfg.asr_model_size,
                "asr_device": cfg.asr_device,
                "asr_compute_type": cfg.asr_compute_type,
                "asr_beam_size": cfg.asr_beam_size,
                "streaming_step_seconds": cfg.streaming_step_seconds,
                "streaming_window_seconds": cfg.streaming_window_seconds,
                "streaming_silence_final_seconds": cfg.streaming_silence_final_seconds,
                "vad_threshold": cfg.vad_threshold,
                "extra_terms": extra_terms or [],
            },
            base_dir=log_dir or LOG_DIR,
        )
        self.stop_event = asyncio.Event()
        self._state: str | None = None
        self._committed = ""

    # ---------- kirim ke client ----------
    async def _send(self, payload: dict[str, Any]) -> bool:
        """Kirim JSON; False jika client sudah putus (tidak boleh membuat sesi crash)."""
        try:
            await self.ws.send_json(payload)
            return True
        except Exception:
            return False

    async def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            await self._send({"type": "status", "state": state})

    async def _emit(self, result: StepResult | StreamingUpdate) -> None:
        if isinstance(result, StepResult):
            rec = self.tracker.record(result)
            update = result.update
            payload = result.to_dict()
            payload["server_e2e_ms"] = (
                None if rec.server_e2e_ms is None else round(rec.server_e2e_ms, 2)
            )
        else:  # hasil flush() saat sesi berakhir
            update = result
            payload = update.to_dict()
        payload["type"] = "transcript"
        if update.final_text:
            self.logger.add_final(update.final_text, update.committed_audio_sec)
        self._committed = update.committed_transcript
        await self._send(payload)

    # ---------- dua pekerjaan yang berjalan bersamaan ----------
    async def _stream_loop(self) -> None:
        """Tiap `step_seconds`: jalankan streamer.step() lalu kirim hasilnya."""
        while not self.stop_event.is_set():
            t0 = time.monotonic()
            try:
                result = await self.streamer.step()
                if result is not None:
                    await self._emit(result)
                    busy = result.in_speech or bool(result.update.partial_text)
                    await self._set_state("processing" if busy else "listening")
            except Exception as exc:  # satu langkah gagal tidak boleh mematikan sesi
                logger.exception("Langkah streaming gagal: %s", exc)
                await self._send({"type": "error", "message": f"Langkah ASR gagal: {exc}"})

            remaining = self.step_seconds - (time.monotonic() - t0)
            if remaining > 0:
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(0)  # langkah melebihi jatah waktu: beri kesempatan loop lain

    async def _receive_loop(self) -> str:
        """Terima frame audio & pesan kontrol. Return alasan berhenti."""
        while True:
            try:
                msg = await self.ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                return "disconnect"
            if msg["type"] == "websocket.disconnect":
                return "disconnect"

            data = msg.get("bytes")
            if data:
                self.buffer.write_bytes(data)
                self.tracker.mark_audio(self.buffer.total_samples)
                continue

            text = msg.get("text")
            if text:
                try:
                    ctrl = json.loads(text)
                except json.JSONDecodeError:
                    await self._send({"type": "error", "message": "Pesan teks harus berupa JSON."})
                    continue
                if isinstance(ctrl, dict) and ctrl.get("type") == "stop":
                    return "stop"

    # ---------- siklus hidup sesi ----------
    async def run(self) -> None:
        cfg = settings
        await self._send(
            {
                "type": "ready",
                "session_id": self.session_id,
                "topic": self.topic,
                "sample_rate": self.sr,
                "step_seconds": self.step_seconds,
                "window_seconds": cfg.streaming_window_seconds,
                "silence_final_seconds": cfg.streaming_silence_final_seconds,
            }
        )
        await self._set_state("listening")

        stream_task = asyncio.create_task(self._stream_loop())
        reason = "disconnect"
        try:
            reason = await self._receive_loop()
        finally:
            self.stop_event.set()
            await stream_task  # tunggu langkah yang sedang berjalan selesai

        try:  # finalkan sisa teks
            await self._emit(await self.streamer.finish())
        except Exception as exc:
            logger.exception("finish() gagal: %s", exc)

        await self._set_state("stopped")
        log_dir = None
        try:
            log_dir = self.logger.save(self._committed, self.tracker, reason)
        except Exception as exc:
            logger.exception("Gagal menyimpan log sesi: %s", exc)

        await self._send(
            {
                "type": "stopped",
                "reason": reason,
                "committed_transcript": self._committed,
                "summary": self.tracker.summary(),
                "log_dir": str(log_dir) if log_dir else None,
            }
        )
        try:
            await self.ws.close()
        except Exception:
            pass


@router.websocket("/ws/stream")
async def ws_stream(
    websocket: WebSocket,
    topic: str | None = None,
    extra_terms: str | None = None,
) -> None:
    await websocket.accept()

    resolved_topic = resolve_topic(topic or settings.asr_default_topic)
    terms = [t.strip() for t in extra_terms.split(",") if t.strip()] if extra_terms else None

    engine = getattr(websocket.app.state, "asr_engine", None) or get_asr_engine(settings)
    try:
        if not engine.is_loaded:
            await asyncio.to_thread(engine.load)
        # Model Silero dimuat per sesi (di thread, agar event loop tidak membeku).
        prob_fn = await asyncio.to_thread(make_silero_prob_fn)
    except Exception as exc:
        logger.exception("Gagal menyiapkan ASR/VAD: %s", exc)
        try:
            await websocket.send_json(
                {"type": "error", "message": f"Gagal menyiapkan ASR/VAD: {exc}"}
            )
            await websocket.close(code=1011)
        except Exception:
            pass
        return

    session = StreamSession(
        websocket, engine, prob_fn, topic=resolved_topic, extra_terms=terms
    )
    await session.run()