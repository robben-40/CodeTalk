"""Client LLM untuk Smart Note (FR07). Hanya dipakai SETELAH ASR lokal selesai.

Konfigurasi dibaca dari app.config.settings, yang memuat file .env:
    LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL, OPENAI_API_KEY, OPENAI_MODEL
    
Opsional (belum ada di Settings;):
    llm_timeout_seconds / LLM_TIMEOUT_S   batas waktu TOTAL request  (default: 55; frontend membatalkan di 60 dtk)
    llm_max_chars       / LLM_MAX_CHARS   batas panjang transkrip  (default: 60000, bagian terbaru dipakai)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field

import httpx

from .prompts import SYSTEM_PROMPT, build_user_prompt, resolve_course

DEFAULT_MODELS = {"gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini"}
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class LLMError(RuntimeError):
    """Kegagalan saat memanggil / mem-parsing respons LLM."""


class LLMConfigError(LLMError):
    """Konfigurasi LLM (provider / API key) belum benar."""


@dataclass
class SmartNote:
    corrected_transcript: str = ""
    corrections: list[dict] = field(default_factory=list)
    summary_points: list[str] = field(default_factory=list)
    code_snippets: list[dict] = field(default_factory=list)
    markdown: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    truncated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- parsing helpers
def _extract_json(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Respons LLM bukan JSON yang valid.") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            raise LLMError("Respons LLM bukan JSON yang valid.") from None
    if not isinstance(data, dict):
        raise LLMError("Respons LLM harus berupa objek JSON.")
    return data


def _normalize(data: dict) -> dict:
    corrections = [
        {"wrong": str(c["wrong"]).strip(), "correct": str(c["correct"]).strip()}
        for c in data.get("corrections") or []
        if isinstance(c, dict) and c.get("wrong") and c.get("correct")
    ]
    snippets = [
        {
            "title": str(s.get("title") or "Snippet").strip(),
            "language": str(s.get("language") or "pseudocode").strip(),
            "code": str(s["code"]).strip("\n"),
        }
        for s in data.get("code_snippets") or []
        if isinstance(s, dict) and s.get("code")
    ]
    points = [str(p).strip() for p in data.get("summary_points") or [] if str(p).strip()]
    return {
        "corrections": corrections,
        "summary_points": points,
        "code_snippets": snippets,
    }


def apply_corrections(transcript: str, corrections: list[dict]) -> str:
    """Terapkan koreksi istilah ke transkrip di sisi server (tanpa meminta LLM menulis ulang
    seluruh transkrip, yang lambat dan bisa terpotong pada sesi panjang)."""
    text = transcript
    for c in sorted(corrections, key=lambda c: len(c["wrong"]), reverse=True):  # yang terpanjang dulu
        pattern = re.compile(rf"(?<!\w){re.escape(c['wrong'])}(?!\w)", re.IGNORECASE)
        text = pattern.sub(lambda _m, repl=c["correct"]: repl, text)
    return text


def render_markdown(note: dict, course_context: str) -> str:
    """Susun catatan menjadi Markdown (dipakai panel kanan UI dan export .md, FR08)."""
    lines = [f"# Catatan Kuliah: {course_context or 'Umum'}", ""]
    lines.append("## Ringkasan Konsep")
    lines += [f"- {p}" for p in note["summary_points"]] or ["_Belum ada poin materi._"]
    if note["code_snippets"]:
        lines += ["", "## Kode / Pseudocode"]
        for s in note["code_snippets"]:
            lines += ["", f"### {s['title']}", f"```{s['language']}", s["code"], "```"]
    if note["corrections"]:
        # Daftar, bukan tabel: SmartNotesPanel (react-markdown tanpa remark-gfm) tidak merender tabel.
        lines += ["", "## Koreksi Istilah", ""]
        lines += [f"- {c['wrong']} → **{c['correct']}**" for c in note["corrections"]]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- client
def _settings():
    """Ambil Settings dari app.config ; None jika tidak tersedia."""
    try:
        from app.config import settings

        return settings
    except Exception:
        return None


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_chars: int | None = None,
    ) -> None:
        cfg = _settings()
        self.provider = str(provider or getattr(cfg, "llm_provider", None) or os.getenv("LLM_PROVIDER") or "gemini").lower()
        if self.provider not in DEFAULT_MODELS:
            raise LLMConfigError(f"LLM_PROVIDER tidak dikenal: {self.provider!r} (pakai gemini/openai).")
        key_env = f"{self.provider.upper()}_API_KEY"
        self.api_key = api_key or getattr(cfg, f"{self.provider}_api_key", None) or os.getenv(key_env) or ""
        if not self.api_key:
            raise LLMConfigError(f"{key_env} belum diisi. Isi di file .env (salin dari .env.example).")
        self.model = model or getattr(cfg, f"{self.provider}_model", None) or DEFAULT_MODELS[self.provider]
        self.timeout = float(timeout or getattr(cfg, "llm_timeout_seconds", None) or os.getenv("LLM_TIMEOUT_S") or 55)
        self.max_chars = int(max_chars or getattr(cfg, "llm_max_chars", None) or os.getenv("LLM_MAX_CHARS") or 60000)

    async def generate_notes(self, transcript: str, course_context: str = "Umum") -> SmartNote:
        transcript = transcript.strip()
        if not transcript:
            raise LLMError("Transkrip kosong.")
        truncated = len(transcript) > self.max_chars
        if truncated:
            transcript = transcript[-self.max_chars :]  # pertahankan bagian terbaru

        user_prompt = build_user_prompt(transcript, course_context)
        start = time.perf_counter()

        async def _call() -> str:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.provider == "gemini":
                    return await self._call_gemini(client, user_prompt)
                return await self._call_openai(client, user_prompt)

        try:  # batas total termasuk semua retry; frontend sudah menyerah di 60 detik
            raw = await asyncio.wait_for(_call(), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise LLMError(f"LLM tidak merespons dalam {self.timeout:g} detik.") from None
        latency_ms = (time.perf_counter() - start) * 1000

        note = _normalize(_extract_json(raw))
        note["corrected_transcript"] = apply_corrections(transcript, note["corrections"])
        return SmartNote(
            **note,
            markdown=render_markdown(note, resolve_course(course_context)[0]),
            provider=self.provider,
            model=self.model,
            latency_ms=round(latency_ms, 1),
            truncated=truncated,
        )

    # ------------------------------------------------------------ providers
    async def _call_gemini(self, client: httpx.AsyncClient, user_prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        data = (await self._post(client, url, headers, payload)).json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Gemini tidak mengembalikan kandidat: {str(data)[:200]}") from None
        return "".join(p.get("text", "") for p in parts)

    async def _call_openai(self, client: httpx.AsyncClient, user_prompt: str) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = (await self._post(client, url, headers, payload)).json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Respons OpenAI tidak valid: {str(data)[:200]}") from None

    async def _post(self, client, url, headers, payload) -> httpx.Response:
        last_error = "tidak diketahui"
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{type(exc).__name__}"
            else:
                if resp.status_code < 300:
                    return resp
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code not in RETRY_STATUS:
                    break
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(1.5 * (2**attempt))
        raise LLMError(f"Gagal memanggil {self.provider}: {last_error}")
