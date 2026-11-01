"""Carga data/fmc130_parameters.json en MongoDB (colección configurada en .env).

- _id determinista (hash de sección, subsección, ID, opción y nombre): reejecutar no duplica.
- Actualiza solo los campos del documento; conserva `embedding` si ya existe.
- Construye `embedding_text`, el texto que se vectorizará en la fase 3.

Uso:
    .venv/bin/python scripts/load_mongo.py
"""

from __future__ import annotations

import hashlib
import json
import sys

from pymongo import MongoClient, UpdateOne

from config import ROOT, load_env

DATA = ROOT / "data" / "fmc130_parameters.json"


def make_id(rec: dict) -> str:
    raw = "|".join(
        str(rec.get(k) or "")
        for k in ("section", "subsection", "parameter_id", "value_description", "parameter_name_en")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def embedding_text(rec: dict) -> str:
    section = rec["section"] + (f" / {rec['subsection']}" if rec.get("subsection") else "")
    rng = f"{rec.get('value_min') or ''}–{rec.get('value_max') or ''}"
    parts = [
        f"Parámetro {rec['parameter_id']}: {rec['parameter_name_es']} ({rec['parameter_name_en']}).",
        f"Sección: {section}.",
        f"Tipo: {rec.get('parameter_type') or '-'}, valor por defecto: {rec.get('default_value') or '-'}, rango: {rng}.",
    ]
    if rec.get("value_description"):
        parts.append(f"Opción de valor: {rec['value_description']}.")
    return " ".join(parts)


def to_document(rec: dict) -> dict:
    doc = {
        "section": rec["section"],
        "subsection": rec.get("subsection"),
        "parameter_id": rec["parameter_id"],
        "parameter_type": rec.get("parameter_type"),
        "default_value": rec.get("default_value"),
        "value_min": rec.get("value_min"),
        "value_max": rec.get("value_max"),
        "value_description": rec.get("value_description"),
        "parameter_name_en": rec["parameter_name_en"],
        "parameter_name_es": rec["parameter_name_es"],
        "embedding_text": embedding_text(rec),
        "source": "https://wiki.teltonika-gps.com/view/FMC130_Parameter_list",
    }
    return doc


def main() -> int:
    env = load_env()
    uri = env.get("MONGODB_URI")
    if not uri:
        print("Falta MONGODB_URI en .env", file=sys.stderr)
        return 1
    db_name = env.get("MONGODB_DATABASE", "fmc130_rag")
    coll_name = env.get("MONGODB_COLLECTION", "parameters")

    records = json.loads(DATA.read_text(encoding="utf-8"))
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    coll = client[db_name][coll_name]

    ops = []
    for rec in records:
        doc = to_document(rec)
        ops.append(UpdateOne({"_id": make_id(rec)}, {"$set": doc}, upsert=True))
    result = coll.bulk_write(ops, ordered=False)

    coll.create_index("parameter_id")
    coll.create_index([("section", 1), ("subsection", 1)])

    total = coll.count_documents({})
    with_emb = coll.count_documents({"embedding": {"$exists": True}})
    print(f"Base: {db_name}.{coll_name}")
    print(f"Upserts: insertados={result.upserted_count} modificados={result.modified_count} sin cambios={result.matched_count - result.modified_count}")
    print(f"Documentos totales: {total} | con embedding: {with_emb}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    raise SystemExit(main())
