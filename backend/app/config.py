"""Configuración del backend leída de variables de entorno (inyectadas por docker compose desde .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-haiku-5-5"))
    # Embeddings locales (ver app/embeddings.py): EMBEDDING_MODEL y FASTEMBED_CACHE_PATH se leen allí.
    mongodb_uri: str = field(default_factory=lambda: _env("MONGODB_URI"))
    mongodb_database: str = field(default_factory=lambda: _env("MONGODB_DATABASE", "fmc130_rag"))
    mongodb_collection: str = field(default_factory=lambda: _env("MONGODB_COLLECTION", "parameters"))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in _env("CORS_ORIGINS", "https://localhost:4443").split(",") if o.strip())
    )
    # Seguridad
    rate_limit_per_minute: int = field(default_factory=lambda: int(_env("RATE_LIMIT_PER_MINUTE", "100")))
    max_body_bytes: int = field(default_factory=lambda: int(_env("MAX_BODY_BYTES", "2048")))
    # Redes de proxies de confianza (el frontend). Solo ellas pueden fijar X-Real-IP.
    trusted_proxies: str = field(default_factory=lambda: _env("TRUSTED_PROXIES", "172.30.0.10/32"))
    enable_docs: bool = field(default_factory=lambda: _env("ENABLE_DOCS", "false").lower() == "true")


settings = Settings()
