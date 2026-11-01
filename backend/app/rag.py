"""Pipeline RAG: consulta -> embedding -> $vectorSearch -> selección con Claude -> respuesta formateada.

Garantía de formato: Claude solo elige un candidato (número). La línea de respuesta
`ParameterID: X Value: Y` se arma en código a partir de los campos almacenados en MongoDB,
así que el formato es siempre exacto.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pymongo import MongoClient

from .config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
INDEX_NAME = "parameters_vector_index"
TOP_K = 8
NOT_FOUND_ANSWER = "No encontré un parámetro que responda a tu consulta."

SELECTOR_SYSTEM_PROMPT = """Eres un asistente de soporte técnico para configurar el dispositivo Teltonika FMC130.
Recibirás una pregunta del usuario en español y una lista numerada de candidatos tomados de la documentación oficial
(parámetros y sus opciones de valor).
Tu tarea: elegir el número del candidato que responde exactamente a la pregunta, considerando la opción de valor correcta.
- Si ningún candidato corresponde a la pregunta, responde con 0.
- No inventes parámetros ni valores que no estén en la lista.
Responde ÚNICAMENTE con un objeto JSON con esta forma: {"candidate": <número>}"""


class RagError(Exception):
    """Error controlado que el API convierte en respuesta HTTP."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Candidate:
    index: int
    parameter_id: str
    parameter_name_es: str
    parameter_name_en: str
    section: str
    subsection: str | None
    value_description: str | None
    parameter_type: str | None
    default_value: str | None
    value_min: str | None
    value_max: str | None
    score: float


@lru_cache(maxsize=1)
def _collection():
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
    return client[settings.mongodb_database][settings.mongodb_collection]


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise
    raise RuntimeError("reintentos agotados")


def embed_query(text: str) -> list[float]:
    if not settings.openrouter_api_key:
        raise RagError("OPENROUTER_API_KEY no configurada", status_code=503)
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-OpenRouter-Title": settings.openrouter_site_name,
    }
    try:
        body = _post_json(
            OPENROUTER_URL,
            headers,
            {"model": settings.openrouter_embedding_model, "input": [text], "encoding_format": "float"},
        )
    except (urllib.error.URLError, RuntimeError, urllib.error.HTTPError) as exc:
        raise RagError(f"Error al calcular el embedding: {exc}", status_code=503) from exc
    return body["data"][0]["embedding"]


def vector_search(vector: list[float], k: int = TOP_K) -> list[Candidate]:
    pipeline = [
        {
            "$vectorSearch": {
                "index": INDEX_NAME,
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": max(50, k * 10),
                "limit": k,
            }
        },
        {
            "$project": {
                "_id": 0,
                "parameter_id": 1,
                "parameter_name_es": 1,
                "parameter_name_en": 1,
                "section": 1,
                "subsection": 1,
                "value_description": 1,
                "parameter_type": 1,
                "default_value": 1,
                "value_min": 1,
                "value_max": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    rows = list(_collection().aggregate(pipeline))
    return [
        Candidate(
            index=i,
            parameter_id=r["parameter_id"],
            parameter_name_es=r["parameter_name_es"],
            parameter_name_en=r["parameter_name_en"],
            section=r["section"],
            subsection=r.get("subsection"),
            value_description=r.get("value_description"),
            parameter_type=r.get("parameter_type"),
            default_value=r.get("default_value"),
            value_min=r.get("value_min"),
            value_max=r.get("value_max"),
            score=float(r["score"]),
        )
        for i, r in enumerate(rows, 1)
    ]


def _candidate_line(c: Candidate) -> str:
    section = c.section + (f" / {c.subsection}" if c.subsection else "")
    option = c.value_description or "sin opciones (valor libre)"
    return (
        f"{c.index}. ID {c.parameter_id} | {c.parameter_name_es} ({c.parameter_name_en}) | "
        f"Sección: {section} | Opción: {option} | Tipo: {c.parameter_type or '-'} | "
        f"Por defecto: {c.default_value or '-'} | Rango: {c.value_min or '-'}–{c.value_max or '-'}"
    )


def select_candidate(question: str, candidates: list[Candidate]) -> int:
    """Pide a Claude el número del candidato correcto. Devuelve 0 si ninguno aplica."""
    if not settings.anthropic_api_key:
        raise RagError("ANTHROPIC_API_KEY no configurada", status_code=503)
    user_content = (
        f"Pregunta: {question}\n\nCandidatos:\n" + "\n".join(_candidate_line(c) for c in candidates)
    )
    payload = {
        "model": settings.anthropic_model,
        # Holgura suficiente: el modelo puede emitir bloques de razonamiento antes del JSON.
        "max_tokens": 1024,
        "system": SELECTOR_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
        # Nota: no se envía `temperature`; los modelos Claude 5 lo rechazan (HTTP 400).
    }
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        body = _post_json(ANTHROPIC_URL, headers, payload, timeout=60)
    except (urllib.error.URLError, RuntimeError, urllib.error.HTTPError) as exc:
        raise RagError(f"Error al consultar Claude: {exc}", status_code=502) from exc

    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise RagError("Respuesta de Claude sin JSON válido", status_code=502)
    try:
        choice = int(json.loads(match.group(0))["candidate"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RagError("Respuesta de Claude con formato inesperado", status_code=502) from exc
    if not 0 <= choice <= len(candidates):
        raise RagError("Claude eligió un candidato fuera de rango", status_code=502)
    return choice


_VALUE_CODE = re.compile(r"^\s*(-?\d+)\s*(?:[–-]|$)")


def value_code(value_description: str | None) -> str | None:
    """Extrae el código numérico de una opción, p. ej. '1 – Ignition' -> '1'."""
    if not value_description:
        return None
    m = _VALUE_CODE.match(value_description)
    return m.group(1) if m else None


def format_answer(c: Candidate) -> str:
    code = value_code(c.value_description)
    if code is None:
        # Parámetro de valor libre o rango: se indica el rango en lugar de un código de opción.
        return f"ParameterID: {c.parameter_id} Value: <{c.value_min}-{c.value_max}>"
    return f"ParameterID: {c.parameter_id} Value: {code}"


def answer_question(question: str) -> dict[str, Any]:
    vector = embed_query(question)
    candidates = vector_search(vector, TOP_K)
    if not candidates:
        return {"answer": NOT_FOUND_ANSWER, "found": False, "parameter_id": None, "value": None, "candidates": []}

    choice = select_candidate(question, candidates)
    chosen = candidates[choice - 1] if choice else None
    if chosen is None:
        return {"answer": NOT_FOUND_ANSWER, "found": False, "parameter_id": None, "value": None,
                "candidates": [_public(c) for c in candidates]}

    return {
        "answer": format_answer(chosen),
        "found": True,
        "parameter_id": chosen.parameter_id,
        "value": value_code(chosen.value_description),
        "parameter_name_es": chosen.parameter_name_es,
        "option": chosen.value_description,
        "section": chosen.section,
        "candidates": [_public(c) for c in candidates],
    }


def _public(c: Candidate) -> dict[str, Any]:
    return {
        "index": c.index,
        "parameter_id": c.parameter_id,
        "parameter_name_es": c.parameter_name_es,
        "option": c.value_description,
        "score": round(c.score, 4),
    }
