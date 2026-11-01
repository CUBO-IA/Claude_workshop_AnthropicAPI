"""Extrae las 22 tablas de parámetros del FMC130 desde la wiki de Teltonika.

Fuente de verdad: https://wiki.teltonika-gps.com/view/FMC130_Parameter_list
Salida: data/fmc130_parameters.json (un registro por fila de parámetro/opción).

Uso:
    python3 scripts/extract_fmc130.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, Tag

SOURCE_URL = "https://wiki.teltonika-gps.com/view/FMC130_Parameter_list"
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "fmc130_parameters.json"

# Secciones de nivel 2 cuyas tablas van directamente bajo el encabezado.
WANT_H2 = {"System parameters", "GPRS parameters", "SMS/Call settings"}

# Subsecciones (nivel 3) incluidas. Las 22 tablas pedidas.
WANT_H3 = {
    # Data acquisition mode parameters
    'Home Network GSM operator code "Vehicle on STOP" parameters',
    'Home Network GSM operator code "Vehicle MOVING" parameters',
    'Roaming Network GSM operator code "Vehicle on STOP" parameters',
    'Roaming Network GSM operator code "Vehicle MOVING" parameters',
    'Unknown Network GSM operator code "Vehicle on STOP" parameters',
    'Unknown Network GSM operator code "Vehicle MOVING" parameters',
    # Features parameters (sin "DOUT control via call", fuera de la lista)
    "Green driving parameters",
    "Overspeeding scenario parameters",
    "Jamming scenario parameters",
    "Immobilizer scenario parameters",
    "DOUT 1 Output type",
    "iButton read notification",
    # Trip/Odometer
    "Trip scenario parameters",
    "Advanced trip scenario parameters",
    "Odometer parameters",
    "Private/Business mode scenario parameters",
    # Accelerometer features
    "Unplug Detection",
    "Towing Detection",
    "Crash Detection",
    "Excessive Idling",
    "Motorcycle Fall Detection",
}

# 22 temas pedidos = 41 tablas: System 9 + GPRS 6 + SMS/Call 5 + Data acquisition 6
# + Features 6 + Trip/Odometer 4 + Accelerometer 5.
EXPECTED_TABLES = 41
FIELDS = [
    "parameter_id",
    "parameter_type",
    "default_value",
    "value_min",
    "value_max",
    "value_description",
    "parameter_name_en",
]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "fmc130-rag-extractor/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")


def expand_table(table: Tag) -> tuple[list[list[str]], int]:
    """Devuelve la tabla como rejilla completa (rowspan/colspan propagados).

    Retorna (filas, índice_primera_fila_de_datos). Las filas de encabezado son
    las que aparecen antes de la primera fila con celdas <td>.
    """
    grid: dict[tuple[int, int], str] = {}
    trs = table.find_all("tr")
    first_data = None
    for r, tr in enumerate(trs):
        if first_data is None and tr.find("td", recursive=False):
            first_data = r
        c = 0
        for cell in tr.find_all(["th", "td"], recursive=False):
            while (r, c) in grid:
                c += 1
            text = clean(cell.get_text(" ", strip=True))
            rs = int(cell.get("rowspan", 1) or 1)
            cs = int(cell.get("colspan", 1) or 1)
            for i in range(rs):
                for j in range(cs):
                    grid[(r + i, c + j)] = text
            c += cs
    if first_data is None:
        first_data = len(trs)
    n_rows = len(trs)
    n_cols = 1 + max((c for (_, c) in grid), default=-1)
    rows = [[grid.get((r, c), "") for c in range(n_cols)] for r in range(n_rows)]
    return rows, first_data


def column_map(header_rows: list[list[str]], n_cols: int) -> dict[str, int]:
    """Asigna cada columna a un campo normalizado usando las filas de encabezado."""
    mapping: dict[str, int] = {}
    for c in range(n_cols):
        labels = [clean(h[c]).lower() for h in header_rows if c < len(h) and h[c]]
        joined = " | ".join(labels)
        if "parameter name" in joined:
            mapping.setdefault("parameter_name_en", c)
        elif "parameter id" in joined and "parameter_id" not in mapping:
            mapping["parameter_id"] = c
        elif "parameter type" in joined:
            mapping.setdefault("parameter_type", c)
        elif "default" in joined:
            mapping.setdefault("default_value", c)
        elif "min" in labels:
            mapping.setdefault("value_min", c)
        elif "max" in labels:
            mapping.setdefault("value_max", c)
        elif labels and labels[-1] == "value":
            mapping.setdefault("value_description", c)
    return mapping


def extract_table(table: Tag, section: str, subsection: str | None) -> list[dict]:
    rows, first_data = expand_table(table)
    header_rows = rows[:first_data]
    data_rows = rows[first_data:]
    if not data_rows:
        return []
    n_cols = len(data_rows[0])
    mapping = column_map(header_rows, n_cols)
    if "parameter_id" not in mapping or "parameter_name_en" not in mapping:
        raise ValueError(f"Encabezado no reconocido en {section} / {subsection}: {header_rows}")

    records = []
    for row in data_rows:
        rec = {"section": section, "subsection": subsection}
        for field in FIELDS:
            idx = mapping.get(field)
            rec[field] = clean(row[idx]) if idx is not None and idx < len(row) else None
        if not rec["parameter_id"] or not rec["parameter_name_en"]:
            continue
        records.append(rec)
    return records


def main() -> int:
    html = fetch_html(SOURCE_URL)
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one(".mw-parser-output")
    if root is None:
        print("No se encontró el contenido de la página", file=sys.stderr)
        return 1

    h2 = None
    h3 = None
    selected: list[dict] = []
    tables_used: list[tuple[str, str | None]] = []

    for el in root.find_all(["h2", "h3", "table"]):
        if el.name == "h2":
            h2 = clean(el.get_text(" ", strip=True).replace("[edit]", ""))
            h3 = None
            continue
        if el.name == "h3":
            h3 = clean(el.get_text(" ", strip=True).replace("[edit]", ""))
            continue
        if "wikitable" not in (el.get("class") or []):
            continue

        if h3 in WANT_H3:
            section, subsection = h2, h3
        elif h3 is None and h2 in WANT_H2:
            section, subsection = h2, None
        else:
            continue

        tables_used.append((section, subsection))
        selected.extend(extract_table(el, section, subsection))

    # Validación
    problems = []
    if len(tables_used) != EXPECTED_TABLES:
        problems.append(f"Tablas encontradas: {len(tables_used)}, esperadas: {EXPECTED_TABLES}")
    ids = [r for r in selected if r["parameter_id"] == "138"]
    if not any(r["value_description"] and r["value_description"].startswith("1") and "Ignition" in r["value_description"] for r in ids):
        problems.append("No se encontró ParameterID 138 con valor 1 – Ignition")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Tablas incluidas: {len(tables_used)}")
    print(f"Registros: {len(selected)}")
    print(f"Salida: {OUTPUT}")
    for key in dict.fromkeys(tables_used):  # sin duplicados, en orden
        section, sub = key
        n = sum(1 for r in selected if (r["section"], r["subsection"]) == key)
        print(f"  - {section} / {sub or '-'}: {n}")
    if problems:
        print("ADVERTENCIAS:", *problems, sep="\n  ")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
