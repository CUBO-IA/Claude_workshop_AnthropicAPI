"""API del chatbot de soporte FMC130 (solo responde la pregunta; sin autenticación ni historial)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .config import settings
from .rag import RagError, answer_question
from .security import SecurityMiddleware, parse_networks

app = FastAPI(
    title="FMC130 Soporte RAG",
    version="0.2.0",
    # La documentación interactiva no se expone salvo que se active explícitamente.
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.add_middleware(
    SecurityMiddleware,
    rate_limit_per_minute=settings.rate_limit_per_minute,
    max_body_bytes=settings.max_body_bytes,
    trusted_proxies=parse_networks(settings.trusted_proxies),
)


class ChatRequest(BaseModel):
    model_config = {"extra": "forbid"}

    question: str = Field(min_length=3, max_length=500)

    @field_validator("question")
    @classmethod
    def no_control_chars(cls, value: str) -> str:
        if any(ord(ch) < 32 and ch not in "\t\n" for ch in value):
            raise ValueError("La pregunta contiene caracteres no permitidos.")
        return value.strip()


class ChatResponse(BaseModel):
    answer: str
    found: bool
    parameter_id: str | None = None
    value: str | None = None
    parameter_name_es: str | None = None
    option: str | None = None
    section: str | None = None
    candidates: list[dict] = []


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # No se devuelven trazas ni detalles internos al cliente.
    return JSONResponse(status_code=500, content={"detail": "Error interno del servicio."})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        result = answer_question(req.question)
    except RagError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
    return ChatResponse(**result)
