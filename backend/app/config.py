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
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    openrouter_embedding_model: str = field(
        default_factory=lambda: _env("OPENROUTER_EMBEDDING_MODEL", "nvidia/nemotron-3.5-embed-1b:free")
    )
    openrouter_site_url: str = field(default_factory=lambda: _env("OPENROUTER_SITE_URL", "http://localhost:3000"))
    openrouter_site_name: str = field(default_factory=lambda: _env("OPENROUTER_SITE_NAME", "FMC130 Soporte RAG"))
    mongodb_uri: str = field(default_factory=lambda: _env("MONGODB_URI"))
    mongodb_database: str = field(default_factory=lambda: _env("MONGODB_DATABASE", "fmc130_rag"))
    mongodb_collection: str = field(default_factory=lambda: _env("MONGODB_COLLECTION", "parameters"))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in _env("CORS_ORIGINS", "https://localhost:3443").split(",") if o.strip())
    )


settings = Settings()
