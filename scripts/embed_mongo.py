"""Fase 3: calcula embeddings con OpenRouter (nvidia/nemotron-3.5-embed-1b:free)
y crea el índice vectorial de MongoDB Atlas (local).

- Procesa solo documentos sin embedding para el modelo configurado (reejecutable).
- Detecta la dimensión del vector con la primera respuesta y crea el índice con ella.

Uso:
    .venv/bin/python scripts/embed_mongo.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from config import ROOT, load_env

API_URL = "https://openrouter.ai/api/v1/embeddings"
BATCH_SIZE = 32
INDEX_NAME = "parameters_vector_index"


def embed_batch(env: dict[str, str], model: str, texts: list[str]) -> list[list[float]]:
    payload = {"model": model, "input": texts, "encoding_format": "float"}
    headers = {
        "Authorization": "Bearer " + env["OPENROUTER_API_KEY"],
        "Content-Type": "application/json",
        "HTTP-Referer": env.get("OPENROUTER_SITE_URL", "http://localhost:3000"),
        "X-OpenRouter-Title": env.get("OPENROUTER_SITE_NAME", "FMC130 Soporte RAG"),
    }
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers=headers)
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.load(resp)
            data = sorted(body["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in data]
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(3 * attempt)
                continue
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    raise RuntimeError("OpenRouter: reintentos agotados")


def main() -> int:
    env = load_env()
    model = env.get("OPENROUTER_EMBEDDING_MODEL", "nvidia/nemotron-3.5-embed-1b:free")
    if not env.get("OPENROUTER_API_KEY"):
        print("Falta OPENROUTER_API_KEY en .env", file=sys.stderr)
        return 1

    client = MongoClient(env["MONGODB_URI"], serverSelectionTimeoutMS=10000)
    coll = client[env.get("MONGODB_DATABASE", "fmc130_rag")][env.get("MONGODB_COLLECTION", "parameters")]

    pending = list(coll.find({"embedding_model": {"$ne": model}}, {"embedding_text": 1}))
    print(f"Documentos pendientes de embedding: {len(pending)} (modelo {model})")

    dims = None
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        vectors = embed_batch(env, model, [d["embedding_text"] for d in batch])
        if len(vectors) != len(batch):
            raise RuntimeError(f"Se esperaban {len(batch)} vectores y llegaron {len(vectors)}")
        dims = dims or len(vectors[0])
        for doc, vec in zip(batch, vectors):
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"embedding": vec, "embedding_model": model, "embedding_dims": len(vec)}},
            )
        print(f"  lote {i // BATCH_SIZE + 1}: {len(batch)} vectores")

    stored_dims = coll.find_one({"embedding": {"$exists": True}}, {"embedding_dims": 1})
    if stored_dims is None:
        raise RuntimeError("No hay embeddings almacenados")
    dims = stored_dims["embedding_dims"]

    existing = [ix["name"] for ix in coll.list_search_indexes()]
    if INDEX_NAME not in existing:
        coll.create_search_index(
            SearchIndexModel(
                name=INDEX_NAME,
                type="vectorSearch",
                definition={
                    "fields": [
                        {"type": "vector", "path": "embedding", "numDimensions": dims, "similarity": "cosine"},
                        {"type": "filter", "path": "parameter_id"},
                        {"type": "filter", "path": "section"},
                    ]
                },
            )
        )
        print(f"Índice vectorial creado: {INDEX_NAME} ({dims} dimensiones, coseno)")
    else:
        print(f"Índice vectorial ya existe: {INDEX_NAME}")

    print(f"Documentos con embedding: {coll.count_documents({'embedding_model': model})}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    raise SystemExit(main())
