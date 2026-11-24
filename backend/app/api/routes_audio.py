"""routes_audio.py: endpoint HTTP untuk mengunggah dan mentranskrip file audio secara lokal."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.asr_local.cs_prompts import resolve_topic
from app.asr_local.engine import get_asr_engine
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def _decode_audio_bytes(raw: bytes, sample_rate: int):
    """Dekode bytes file audio (WAV/MP3/M4A/OGG/FLAC/WEBM) ke 1D float32 mono."""
    from faster_whisper.audio import decode_audio

    return decode_audio(io.BytesIO(raw), sampling_rate=sample_rate)


@router.post("/transcribe-audio")
async def transcribe_audio_file(
    request: Request,
    topic: str | None = Query(default=None),
    extra_terms: str | None = Query(default=None),
    filename: str | None = Query(default=None),
) -> dict[str, Any]:
    """Terima file audio mentah (body biner) dan transkripsi memakai model ASR lokal."""
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="File audio kosong.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Ukuran file audio melebihi batas maksimum 50 MB.",
        )

    try:
        audio_f32 = await asyncio.to_thread(
            _decode_audio_bytes, raw, settings.audio_sample_rate
        )
    except Exception as exc:
        logger.warning("Gagal mendekode file audio '%s': %s", filename, exc)
        raise HTTPException(
            status_code=400,
            detail="Format file audio tidak didukung atau rusak. Gunakan WAV, MP3, M4A, OGG, FLAC, atau WEBM.",
        ) from exc

    if audio_f32.size == 0:
        raise HTTPException(
            status_code=400,
            detail="File audio tidak berisi data suara.",
        )

    resolved_topic = resolve_topic(topic or settings.asr_default_topic)
    terms = (
        [t.strip() for t in extra_terms.split(",") if t.strip()]
        if extra_terms
        else None
    )

    engine = getattr(request.app.state, "asr_engine", None) or get_asr_engine(settings)
    try:
        result = await asyncio.to_thread(
            engine.transcribe,
            audio_f32,
            topic=resolved_topic,
            extra_terms=terms,
            sample_rate=settings.audio_sample_rate,
        )
    except Exception as exc:
        logger.exception("Transkripsi file audio gagal: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memproses transkripsi audio: {exc}",
        ) from exc

    payload = result.to_dict()
    payload["filename"] = filename or "uploaded-audio"
    return payload
