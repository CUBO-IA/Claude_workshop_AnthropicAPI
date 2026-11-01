"""Pruebas de aceptación del chatbot FMC130 contra el servicio desplegado (HTTPS).

Requisitos: servicios levantados con docker compose.
Ejecución:
    .venv/bin/python -m pytest tests -v
Variable opcional: BASE_URL (por defecto https://127.0.0.1:4443).

Los criterios de aceptación no estaban definidos por el usuario; estos son los propuestos:
  1. Formato exacto `ParameterID: X Value: Y` (o `Value: <min-max>` para valores libres),
     o el mensaje de "no encontrado" para preguntas fuera de dominio.
  2. Preguntas con respuesta inequívoca devuelven el ID y valor esperados.
  3. Preguntas ambiguas devuelven un ID dentro del conjunto de parámetros válidos.
  4. Misma pregunta, misma respuesta en repetidas ejecuciones (consistencia, sustituye temperatura 0).
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get("BASE_URL", "https://127.0.0.1:4443").rstrip("/")
NOT_FOUND = "No encontré un parámetro que responda a tu consulta."
ANSWER_RE = re.compile(r"^ParameterID: (\d+) Value: (\S+|<[^>]+>)$")
REPEATS = 3

_ctx = ssl._create_unverified_context()  # certificado autofirmado de desarrollo


def ask(question: str) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=json.dumps({"question": question}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=180) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        pytest.fail(f"HTTP {exc.code} para {question!r}: {exc.read()[:200]!r}")


# (pregunta, respuesta exacta esperada | None, IDs válidos | None)
EXACT_CASES = [
    ("¿Como configuro la fuente de movimiento a ignición?", "ParameterID: 138 Value: 1"),
    ("¿Cómo configuro el APN del GPRS?", "ParameterID: 2001 Value: <0-32>"),
    ("¿Qué valor pongo para que el modo privado esté desactivado?", "ParameterID: 11850 Value: 0"),
    ("¿Cómo configuro el acelerómetro para calibración automática?", "ParameterID: 169 Value: 1"),
]

# Preguntas ambiguas: se acepta cualquier ID del conjunto (criterio 3).
AMBIGUOUS_CASES = [
    ("¿Cómo activo la detección de choque?", {"11400", "11406"}),
    ("¿Cómo configuro el parámetro de detección de remolque?", {"11600", "11601", "11602", "11603", "11604", "11605"}),
]

OUT_OF_SCOPE = ["¿Cuál es la receta para hacer un pastel de chocolate?"]

ALL_QUESTIONS = [q for q, _ in EXACT_CASES] + [q for q, _ in AMBIGUOUS_CASES] + OUT_OF_SCOPE


@pytest.mark.parametrize("question,expected", EXACT_CASES)
def test_respuesta_exacta(question, expected):
    data = ask(question)
    assert data["answer"] == expected, f"{question!r}: {data['answer']!r}"


@pytest.mark.parametrize("question,valid_ids", AMBIGUOUS_CASES)
def test_respuesta_ambigua_dentro_de_conjunto(question, valid_ids):
    data = ask(question)
    m = ANSWER_RE.match(data["answer"])
    assert m, f"Formato inesperado: {data['answer']!r}"
    assert m.group(1) in valid_ids, f"ID {m.group(1)} fuera de {sorted(valid_ids)}"


@pytest.mark.parametrize("question", OUT_OF_SCOPE)
def test_fuera_de_dominio(question):
    data = ask(question)
    assert data["answer"] == NOT_FOUND
    assert data["found"] is False


@pytest.mark.parametrize("question", ALL_QUESTIONS)
def test_consistencia_entre_ejecuciones(question):
    answers = {ask(question)["answer"] for _ in range(REPEATS)}
    assert len(answers) == 1, f"Respuestas distintas para {question!r}: {answers}"


@pytest.mark.parametrize("question", [q for q, _ in EXACT_CASES] + [q for q, _ in AMBIGUOUS_CASES])
def test_formato_de_respuesta(question):
    answer = ask(question)["answer"]
    assert ANSWER_RE.match(answer), f"Formato inesperado: {answer!r}"


def test_servicio_https_activo():
    with urllib.request.urlopen(f"{BASE_URL}/api/health", context=_ctx, timeout=10) as resp:
        assert resp.status == 200
        assert json.load(resp) == {"status": "ok"}
