"""Konfigurasi terpusat untuk backend CodeTalk.

Nilai default dapat di-override melalui environment variables atau file `.env`
(misalnya `ASR_MODEL_SIZE=base`).
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Konfigurasi aplikasi backend CodeTalk berbasis pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=(
            str(PROJECT_ROOT / ".env"),
            str(BACKEND_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Aplikasi & Server ---
    app_name: str = "CodeTalk"
    app_version: str = "0.1.0"
    debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("APP_DEBUG", "CODETALK_DEBUG"),
        description="Mode debug/reload server (pakai APP_DEBUG agar tidak bentrok dengan env DEBUG OS).",
    )
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # --- Local ASR Engine (faster-whisper / CTranslate2) ---
    asr_model_size: str = Field(
        default="small",
        validation_alias=AliasChoices("ASR_MODEL_SIZE", "WHISPER_MODEL"),
        description="Ukuran model faster-whisper lokal (tiny, base, small, medium, large-v3).",
    )
    asr_device: Literal["auto", "cpu", "cuda"] = Field(
        default="auto",
        description="Target device inferensi ('auto' memilih GPU/CUDA jika ada, selainnya CPU).",
    )
    asr_compute_type: str = Field(
        default="int8",
        description="Tipe presisi kuantisasi CTranslate2 ('int8' universal untuk CPU & GPU).",
    )
    asr_language: str = Field(
        default="id",
        description="Kode bahasa utama Whisper ('id' untuk Bahasa Indonesia).",
    )
    asr_model_dir: Path = Field(
        default=BACKEND_DIR / "models",
        description="Direktori cache/penyimpanan lokal bobot model faster-whisper.",
    )
    asr_cpu_threads: int = Field(
        default=0,
        ge=0,
        description="Jumlah thread CPU untuk CTranslate2 (0 = otomatis).",
    )
    asr_num_workers: int = Field(
        default=1,
        ge=1,
        description="Jumlah worker inferensi paralel pada WhisperModel.",
    )
    asr_beam_size: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Beam size decoding (1 = greedy tercepat untuk real-time streaming).",
    )
    asr_vad_filter: bool = Field(
        default=True,
        description="Aktifkan filter VAD internal faster-whisper untuk melewatkan segmen hening.",
    )
    asr_condition_on_previous_text: bool = Field(
        default=False,
        description="Nonaktifkan conditioning antar-chunk agar mencegah halusinasi berulang.",
    )
    asr_default_topic: str = Field(
        default="general",
        description="Topik kuliah CS default untuk injeksi initial_prompt code-switching.",
    )
    asr_preload_model: bool = Field(
        default=True,
        description="Muat model ASR saat startup FastAPI agar inferensi pertama tidak lag.",
    )

    # --- Audio & Streaming Policy (16kHz Mono PCM) ---
    audio_sample_rate: int = Field(default=16000, ge=8000)
    audio_channels: int = Field(default=1, ge=1)
    audio_buffer_max_seconds: float = Field(default=30.0, gt=0.0)
    streaming_step_seconds: float = Field(default=0.6, gt=0.0)
    streaming_window_seconds: float = Field(default=6.0, gt=0.5)
    streaming_min_audio_seconds: float = Field(default=0.4, gt=0.0)
    streaming_silence_final_seconds: float = Field(default=1.0, gt=0.0)
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # --- LLM Post-Processing / Smart Note Summarizer ---
    llm_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Izinkan format string dipisah koma di `.env` selain JSON array."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped.startswith("["):
                return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("asr_model_size", "asr_compute_type", "asr_language", mode="before")
    @classmethod
    def _strip_lower(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Kembalikan instance Settings tunggal (cached)."""
    return Settings()


settings = get_settings()
