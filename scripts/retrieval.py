"""Recuperación: embedding local de la consulta + $vectorSearch en MongoDB.

Uso como prueba:
    .venv/bin/python scripts/retrieval.py "¿Cómo configuro la fuente de movimiento a ignición?"
"""

from __future__ import annotations

import sys
from functools import lru_cache

from pymongo import MongoClient

from config import ROOT, load_env
from embed_mongo import INDEX_NAME

sys.path.insert(0, str(ROOT / "backend"))
from app import embeddings  # noqa: E402

_env = load_env()


@lru_cache(maxsize=1)
def _collection():
    client = MongoClient(_env["MONGODB_URI"], serverSelectionTimeoutMS=10000)
    return client[_env.get("MONGODB_DATABASE", "fmc130_rag")][_env.get("MONGODB_COLLECTION", "parameters")]


def search(query: str, k: int = 5) -> list[dict]:
    vector = embeddings.embed_query(query)
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
    return list(_collection().aggregate(pipeline))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "¿Cómo configuro la fuente de movimiento a ignición?"
    for i, r in enumerate(search(q, 5), 1):
        print(f"{i}. score={r['score']:.4f} ID={r['parameter_id']} | {r['parameter_name_es']} | {r.get('value_description')} | {r['section']}")
