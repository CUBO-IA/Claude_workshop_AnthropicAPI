"""Fase 3: calcula embeddings locales (intfloat/multilingual-e5-large, fastembed)
y crea el índice vectorial de MongoDB Atlas (local).

- Procesa solo documentos cuyo embedding no es del modelo configurado (reejecutable).
- Si el índice existe con otra dimensión, lo elimina y lo vuelve a crear.

Uso:
    .venv/bin/python scripts/embed_mongo.py
"""

from __future__ import annotations

import sys
import time

from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from config import ROOT, load_env

sys.path.insert(0, str(ROOT / "backend"))
from app import embeddings  # noqa: E402

BATCH_SIZE = 32
INDEX_NAME = "parameters_vector_index"


def _index_dims(coll) -> int | None:
    for ix in coll.list_search_indexes():
        if ix.get("name") == INDEX_NAME:
            for field in ix.get("latestDefinition", {}).get("fields", []):
                if field.get("type") == "vector":
                    return field.get("numDimensions")
            return -1  # existe pero sin campo vectorial reconocible
    return None


def main() -> int:
    env = load_env()
    model = embeddings.model_name()

    client = MongoClient(env["MONGODB_URI"], serverSelectionTimeoutMS=10000)
    coll = client[env.get("MONGODB_DATABASE", "fmc130_rag")][env.get("MONGODB_COLLECTION", "parameters")]

    pending = list(coll.find({"embedding_model": {"$ne": model}}, {"embedding_text": 1}))
    print(f"Documentos pendientes de embedding: {len(pending)} (modelo {model})")

    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        vectors = embeddings.embed_passages([d["embedding_text"] for d in batch], batch_size=BATCH_SIZE)
        if len(vectors) != len(batch):
            raise RuntimeError(f"Se esperaban {len(batch)} vectores y llegaron {len(vectors)}")
        for doc, vec in zip(batch, vectors):
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"embedding": vec, "embedding_model": model, "embedding_dims": len(vec)}},
            )
        print(f"  lote {i // BATCH_SIZE + 1}: {len(batch)} vectores")

    stored = coll.find_one({"embedding": {"$exists": True}}, {"embedding_dims": 1})
    if stored is None:
        raise RuntimeError("No hay embeddings almacenados")
    dims = stored["embedding_dims"]
    stale = coll.count_documents({"embedding_model": {"$ne": model}})
    if stale:
        raise RuntimeError(f"Quedan {stale} documentos con embeddings de otro modelo")

    current = _index_dims(coll)
    if current == dims:
        print(f"Índice vectorial ya existe: {INDEX_NAME} ({dims} dimensiones)")
    else:
        if current is not None:
            print(f"Eliminando índice con {current} dimensiones: {INDEX_NAME}")
            coll.drop_search_index(INDEX_NAME)
            # La eliminación de índices de búsqueda es asíncrona; esperar a que desaparezca.
            for _ in range(60):
                if _index_dims(coll) is None:
                    break
                time.sleep(2)
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

    print(f"Documentos con embedding: {coll.count_documents({'embedding_model': model})}")
    client.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    raise SystemExit(main())
