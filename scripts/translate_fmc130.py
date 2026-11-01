"""Fase 2: traduce "Parameter name" (inglés) a español con Claude Haiku.

- Traduce solo nombres únicos, en lotes, pidiendo JSON estricto.
- Valida que cada nombre tenga traducción no vacía.
- Cachea el resultado en data/translations_es.json (reejecutar no vuelve a llamar a la API).
- Añade el campo `parameter_name_es` a data/fmc130_parameters.json.

Nota: Claude 5 rechaza el parámetro `temperature`, así que no se envía.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request

from config import ROOT, load_env

DATA = ROOT / "data" / "fmc130_parameters.json"
CACHE = ROOT / "data" / "translations_es.json"
BATCH_SIZE = 40
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """Eres un traductor técnico especializado en dispositivos GPS de rastreo vehicular (Teltonika FMC130).
Traduce al español neutro los nombres de parámetros de configuración que recibirás.
Reglas:
- Usa terminología de telemetría y vehículos comprensible para un técnico hispanohablante.
- Conserva sin traducir las siglas y nombres propios: GSM, GPRS, APN, SMS, GNSS, GPS, DIN, DOUT, CAN, LVCAN, OBD, DTC, AGPS, NTP, BLE, iButton, Teltonika, FMC130, FOTA, ID, UUID, Major, Minor, Eco.
- Mantén el mismo significado y no añadas explicaciones.
- Responde ÚNICAMENTE con un objeto JSON cuyas claves sean los textos originales exactos y cuyos valores sean la traducción. Sin texto adicional ni bloques de código."""


def call_claude(api_key: str, model: str, user_prompt: str) -> str:
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.load(resp)
            return "".join(b.get("text", "") for b in body["content"] if b["type"] == "text")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"Anthropic HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    raise RuntimeError("Anthropic: reintentos agotados")


def parse_json_object(text: str) -> dict[str, str]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Respuesta sin JSON: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def main() -> int:
    env = load_env()
    api_key = env.get("ANTHROPIC_API_KEY", "")
    model = env.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
    if not api_key:
        print("Falta ANTHROPIC_API_KEY en .env", file=sys.stderr)
        return 1

    records = json.loads(DATA.read_text(encoding="utf-8"))
    names = sorted({r["parameter_name_en"] for r in records})
    translations: dict[str, str] = {}
    if CACHE.exists():
        translations = json.loads(CACHE.read_text(encoding="utf-8"))
    pending = [n for n in names if not translations.get(n)]
    print(f"Nombres únicos: {len(names)} | ya traducidos: {len(names) - len(pending)} | pendientes: {len(pending)}")

    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        prompt = "Traduce estos nombres de parámetros:\n" + json.dumps(batch, ensure_ascii=False, indent=2)
        result = parse_json_object(call_claude(api_key, model, prompt))
        for name in batch:
            value = result.get(name)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"Sin traducción válida para: {name!r}")
            translations[name] = value.strip()
        CACHE.write_text(json.dumps(translations, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  lote {i // BATCH_SIZE + 1}: {len(batch)} nombres")

    missing = [n for n in names if not translations.get(n)]
    if missing:
        print("Faltan traducciones:", missing, file=sys.stderr)
        return 2

    for r in records:
        r["parameter_name_es"] = translations[r["parameter_name_en"]]
    DATA.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Registros con parameter_name_es: {len(records)} -> {DATA}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    raise SystemExit(main())
