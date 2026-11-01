"""Pruebas unitarias sin red: extracción del código de opción y formato de la respuesta."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.rag import Candidate, format_answer, value_code  # noqa: E402


def make(value_description, vmin="0", vmax="3", pid="138"):
    return Candidate(
        index=1,
        parameter_id=pid,
        parameter_name_es="X",
        parameter_name_en="X",
        section="S",
        subsection=None,
        value_description=value_description,
        parameter_type="Uint8",
        default_value="0",
        value_min=vmin,
        value_max=vmax,
        score=0.9,
    )


@pytest.mark.parametrize(
    "description,code",
    [
        ("1 – Ignition", "1"),
        ("0 - Disable", "0"),
        ("0 – Disabled", "0"),
        ("8 - CAN Speed", "8"),
        ("-1 – Off", "-1"),
        ("String", None),
        ("mG", None),
        ("", None),
        (None, None),
    ],
)
def test_value_code(description, code):
    assert value_code(description) == code


def test_formato_con_codigo():
    assert format_answer(make("1 – Ignition")) == "ParameterID: 138 Value: 1"


def test_formato_valor_libre_muestra_rango():
    assert format_answer(make("String", vmin="0", vmax="32", pid="2001")) == "ParameterID: 2001 Value: <0-32>"


def test_formato_sin_espacios_extra():
    line = format_answer(make("0 - Disable"))
    assert line == "ParameterID: 138 Value: 0"
    assert line.count(" ") == 3


def test_normalizacion_de_pregunta_ignora_tildes_y_signos():
    from app.rag import normalize_question

    assert normalize_question("¿Cómo configuro la fuente de movimiento a ignición?") == normalize_question(
        "Como configuro la fuente de movimiento a ignicion"
    )
    assert normalize_question("  ¿Cómo  activo   el APN?  ") == "como activo el apn"
