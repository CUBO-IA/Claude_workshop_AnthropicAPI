"""Embeddings locales (fastembed/ONNX, sin red ni cuota de API).

Modelo: intfloat/multilingual-e5-large (1024 dimensiones). Los modelos e5 esperan prefijos:
"query: " para las consultas del usuario y "passage: " para los documentos indexados.
Backend y scripts usan este mismo módulo para que los vectores sean comparables.
"""

from __future__ import annotations

import os
from functools import lru_cache

DEFAULT_MODEL = "intfloat/multilingual-e5-large"
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


def model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    cache_dir = os.environ.get("FASTEMBED_CACHE_PATH") or None
    return TextEmbedding(model_name=model_name(), cache_dir=cache_dir)


def _embed(texts: list[str]) -> list[list[float]]:
    return [vec.tolist() for vec in _model().embed(texts)]


def embed_query(text: str) -> list[float]:
    return _embed([QUERY_PREFIX + text])[0]


def embed_passages(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        out.extend(_embed([PASSAGE_PREFIX + t for t in texts[i : i + batch_size]]))
    return out
