"""Endpoint REST untuk Generate Smart Note (FR07).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import AliasChoices, BaseModel, Field

from app.llm_summarizer.client import LLMClient, LLMConfigError, LLMError

router = APIRouter(prefix="/notes")

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Buat client sekali saja (lazy), agar server tetap bisa start tanpa API key."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


class NoteRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=500_000, description="Kumpulan final transcript (client memotong ke bagian terbaru bila terlalu panjang)")
    topic: str = Field(
        "general",
        max_length=100,
        validation_alias=AliasChoices("topic", "course_context"),
        description="Kunci topik dari GET /topics (mis. data_structures); 'course_context' juga diterima",
    )
    session_id: str | None = None


class Correction(BaseModel):
    wrong: str
    correct: str


class CodeSnippet(BaseModel):
    title: str
    language: str
    code: str


class NoteResponse(BaseModel):
    corrected_transcript: str
    corrections: list[Correction]
    summary_points: list[str]
    code_snippets: list[CodeSnippet]
    markdown: str
    provider: str
    model: str
    latency_ms: float
    truncated: bool
    session_id: str | None = None


@router.post("", response_model=NoteResponse)
@router.post("/generate", response_model=NoteResponse, include_in_schema=False)
async def generate_note(req: NoteRequest) -> NoteResponse:
    if not req.transcript.strip():
        raise HTTPException(status_code=422, detail="Transkrip kosong.")
    try:
        note = await get_llm_client().generate_notes(req.transcript, req.topic)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return NoteResponse(**note.to_dict(), session_id=req.session_id)


@router.get("/health")
async def notes_health() -> dict:
    try:
        client = get_llm_client()
    except LLMConfigError as exc:
        return {"configured": False, "detail": str(exc)}
    return {"configured": True, "provider": client.provider, "model": client.model}
