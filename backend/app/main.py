"""API del chatbot de soporte FMC130 (solo responde la pregunta; sin autenticación ni historial)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .rag import RagError, answer_question

app = FastAPI(title="FMC130 Soporte RAG", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class ChatResponse(BaseModel):
    answer: str
    found: bool
    parameter_id: str | None = None
    value: str | None = None
    parameter_name_es: str | None = None
    option: str | None = None
    section: str | None = None
    candidates: list[dict] = []


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        result = answer_question(req.question.strip())
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ChatResponse(**result)
