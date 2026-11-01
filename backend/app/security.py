"""Controles de seguridad del backend, como middleware ASGI puro:

- Rate limiting por IP de cliente (ventana deslizante de 60 s, por defecto 100 peticiones a /api/chat).
- Límite de tamaño del cuerpo de la petición.
- Cabeceras de seguridad en todas las respuestas.

La IP del cliente solo se toma de X-Real-IP cuando la conexión llega desde un proxy de confianza
(el contenedor del frontend, con IP fija). Así un cliente no puede falsificar su IP.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
from collections import deque
from typing import Awaitable, Callable

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


class SlidingWindowLimiter:
    """Cuenta eventos por clave en una ventana deslizante. Seguro para hilos."""

    def __init__(self, limit: int, window_seconds: float = 60.0, max_keys: int = 10_000):
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Devuelve (permitido, segundos_hasta_reintentar)."""
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        with self._lock:
            if key not in self._hits and len(self._hits) >= self.max_keys:
                self._evict(cutoff)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(0.0, hits[0] + self.window - now)
            hits.append(now)
            return True, 0.0

    def _evict(self, cutoff: float) -> None:
        for k in [k for k, h in self._hits.items() if not h or h[-1] <= cutoff]:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:
            # Caso extremo: se descarta lo más antiguo para acotar la memoria.
            oldest = sorted(self._hits.items(), key=lambda kv: kv[1][-1] if kv[1] else 0)
            for k, _ in oldest[: len(self._hits) - self.max_keys + 1]:
                del self._hits[k]


def parse_networks(spec: str) -> list[ipaddress._BaseNetwork]:
    nets = []
    for part in spec.split(","):
        part = part.strip()
        if part:
            nets.append(ipaddress.ip_network(part, strict=False))
    return nets


def client_ip(scope: Scope, trusted: list[ipaddress._BaseNetwork]) -> str:
    peer = (scope.get("client") or ("unknown", 0))[0]
    try:
        peer_addr = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if any(peer_addr in net for net in trusted):
        for name, value in scope.get("headers", []):
            if name == b"x-real-ip":
                candidate = value.decode("latin-1").strip()
                try:
                    return str(ipaddress.ip_address(candidate))
                except ValueError:
                    break
    return str(peer_addr)


SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
]


class SecurityMiddleware:
    def __init__(
        self,
        app,
        *,
        rate_limit_per_minute: int,
        max_body_bytes: int,
        trusted_proxies: list[ipaddress._BaseNetwork],
        limited_paths: tuple[str, ...] = ("/api/chat",),
    ):
        self.app = app
        self.limiter = SlidingWindowLimiter(rate_limit_per_minute, 60.0)
        self.max_body_bytes = max_body_bytes
        self.trusted = trusted_proxies
        self.limited_paths = limited_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]

        if method == "POST" and path in self.limited_paths:
            ip = client_ip(scope, self.trusted)
            allowed, retry_after = self.limiter.check(ip)
            if not allowed:
                await _json(
                    send,
                    429,
                    {"detail": "Demasiadas peticiones. Intenta de nuevo en un momento."},
                    extra=[(b"retry-after", str(int(retry_after) + 1).encode())],
                )
                return

        if method in ("POST", "PUT", "PATCH"):
            length = dict(scope.get("headers", [])).get(b"content-length")
            if length is not None:
                try:
                    too_big = int(length) > self.max_body_bytes
                except ValueError:
                    too_big = True
                if too_big:
                    await _json(send, 413, {"detail": "La petición es demasiado grande."})
                    return

        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name for name, _ in headers}
                for name, value in SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def _json(send: Send, status: int, body: dict, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(payload)).encode()),
        *SECURITY_HEADERS,
        *(extra or []),
    ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})
