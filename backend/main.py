"""Entry point aplikasi FastAPI backend CodeTalk.

Menyiapkan CORS, preload model ASR lokal saat startup, endpoint `/health`
dan `/topics`, serta slot mounting router dari `app.api.ws_stream` dan
`app.api.routes_notes`.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Pastikan folder `backend/` ada di sys.path baik saat dijalankan dari `backend/`
# (`uvicorn main:app`) maupun dari root repo (`uvicorn backend.main:app`).
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.asr_local.cs_prompts import list_topics  # noqa: E402
from app.asr_local.engine import get_asr_engine  # noqa: E402
from app.config import settings  # noqa: E402

logger = logging.getLogger(__name__)


def _mount_optional_router(
    app: FastAPI,
    module_path: str,
    *,
    prefix: str = "",
    tags: list[str] | None = None,
) -> bool:
    """Mount `router` dari modul API jika sudah diimplementasikan."""
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        logger.warning("Gagal mengimpor modul router '%s': %s", module_path, exc)
        return False

    router = getattr(module, "router", None)
    if isinstance(router, APIRouter):
        app.include_router(router, prefix=prefix, tags=tags)
        logger.info("Router '%s' berhasil dipasang (prefix='%s').", module_path, prefix)
        return True

    logger.info("Router '%s' belum tersedia (menunggu implementasi tim).", module_path)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload model ASR lokal saat startup dan bersihkan saat shutdown."""
    engine = get_asr_engine(settings)
    app.state.asr_engine = engine
    app.state.asr_load_error = None

    if settings.asr_preload_model:
        try:
            await asyncio.to_thread(engine.load)
        except Exception as exc:
            app.state.asr_load_error = str(exc)
            logger.exception("Preload model ASR lokal gagal saat startup: %s", exc)

    try:
        yield
    finally:
        if engine.is_loaded:
            engine.unload()


def create_app() -> FastAPI:
    """Bangun instance FastAPI CodeTalk lengkap dengan middleware dan router."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="CodeTalk local real-time CS lecture ASR and smart note summarizer backend",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, Any]:
        """Cek kesehatan server dan status kesiapan model ASR lokal."""
        engine = getattr(app.state, "asr_engine", None) or get_asr_engine(settings)
        load_error = getattr(app.state, "asr_load_error", None)
        return {
            "status": "degraded" if load_error else "ok",
            "app": settings.app_name,
            "version": settings.app_version,
            "asr": {
                "model_size": settings.asr_model_size,
                "device": settings.asr_device,
                "compute_type": settings.asr_compute_type,
                "language": settings.asr_language,
                "model_loaded": engine.is_loaded,
                "load_time_sec": (
                    round(engine.load_time_sec, 3)
                    if engine.load_time_sec is not None
                    else None
                ),
                "load_error": load_error,
            },
        }

    @app.get("/topics", tags=["asr"])
    def get_cs_topics() -> dict[str, Any]:
        """Kembalikan daftar topik kuliah CS beserta daftar istilah code-switching."""
        return {
            "default_topic": settings.asr_default_topic,
            "topics": list_topics(),
        }

    # Slot router untuk modul tim lain:
    # - Orang 2 (`app/api/ws_stream.py`): definisikan `router = APIRouter()` untuk WebSocket streaming
    # - Orang 4 (`app/api/routes_notes.py`): definisikan `router = APIRouter()` untuk LLM summarizer
    _mount_optional_router(app, "app.api.ws_stream", tags=["stream"])
    _mount_optional_router(app, "app.api.routes_audio", prefix="/api", tags=["asr"])
    _mount_optional_router(app, "app.api.routes_notes", prefix="/api", tags=["notes"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
