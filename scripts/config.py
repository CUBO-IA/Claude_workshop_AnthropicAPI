"""Carga de configuración desde el archivo .env de la raíz del proyecto."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def load_env() -> dict[str, str]:
    """Lee .env y lo vuelca en os.environ (sin sobrescribir variables ya definidas)."""
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values
