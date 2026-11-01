"""Pruebas unitarias sin red de los controles de seguridad del backend."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.security import (  # noqa: E402
    SecurityMiddleware,
    SlidingWindowLimiter,
    client_ip,
    parse_networks,
)


# ---------- Limiter ----------

def test_limite_100_por_minuto():
    lim = SlidingWindowLimiter(limit=100, window_seconds=60)
    results = [lim.check("ip", now=1000.0)[0] for _ in range(105)]
    assert results.count(True) == 100
    assert results.count(False) == 5


def test_limiter_se_recupera_tras_la_ventana():
    lim = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert lim.check("ip", now=0)[0] and lim.check("ip", now=1)[0]
    allowed, retry = lim.check("ip", now=2)
    assert not allowed and 57 < retry <= 58
    assert lim.check("ip", now=61)[0]


def test_limiter_por_ip_independiente():
    lim = SlidingWindowLimiter(limit=1, window_seconds=60)
    assert lim.check("a", now=0)[0]
    assert not lim.check("a", now=1)[0]
    assert lim.check("b", now=1)[0]


def test_limiter_acota_memoria():
    lim = SlidingWindowLimiter(limit=5, window_seconds=60, max_keys=50)
    for i in range(500):
        lim.check(f"ip{i}", now=float(i))
    assert len(lim._hits) <= 50


# ---------- IP de cliente ----------

TRUSTED = parse_networks("172.30.0.10/32")


def _scope(peer, real_ip=None):
    headers = []
    if real_ip is not None:
        headers.append((b"x-real-ip", real_ip.encode()))
    return {"type": "http", "client": (peer, 1234), "headers": headers, "method": "POST", "path": "/api/chat"}


def test_ip_directa_si_el_peer_no_es_proxy():
    # Un cliente externo no puede falsificar X-Real-IP.
    assert client_ip(_scope("203.0.113.7", real_ip="1.2.3.4"), TRUSTED) == "203.0.113.7"


def test_ip_de_x_real_ip_si_el_proxy_es_confiable():
    assert client_ip(_scope("172.30.0.10", real_ip="198.51.100.9"), TRUSTED) == "198.51.100.9"


def test_x_real_ip_invalida_se_ignora():
    assert client_ip(_scope("172.30.0.10", real_ip="no-es-ip"), TRUSTED) == "172.30.0.10"


# ---------- Middleware ----------

async def _run(app, scope, body=b""):
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body_msg = next((m for m in messages if m["type"] == "http.response.body"), {"body": b""})
    return start, body_msg["body"]


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": b"{}"})


def _mw(limit=100, max_body=2048):
    return SecurityMiddleware(
        _ok_app,
        rate_limit_per_minute=limit,
        max_body_bytes=max_body,
        trusted_proxies=TRUSTED,
    )


def _post_scope(content_length=None, peer="203.0.113.50", path="/api/chat"):
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {"type": "http", "method": "POST", "path": path, "client": (peer, 1), "headers": headers}


def test_middleware_devuelve_429_con_retry_after():
    app = _mw(limit=3)
    statuses = []
    for _ in range(4):
        start, _ = asyncio.run(_run(app, _post_scope(content_length=10), body=b"x" * 10))
        statuses.append(start["status"])
    assert statuses == [200, 200, 200, 429]
    start, body = asyncio.run(_run(app, _post_scope(content_length=10), body=b"x" * 10))
    headers = dict(start["headers"])
    assert b"retry-after" in headers
    assert "Demasiadas" in json.loads(body)["detail"]


def test_middleware_rechaza_cuerpo_grande_con_413():
    start, _ = asyncio.run(_run(_mw(max_body=100), _post_scope(content_length=5000), body=b""))
    assert start["status"] == 413


def test_middleware_no_limita_health():
    app = _mw(limit=1)
    scope = {"type": "http", "method": "GET", "path": "/api/health", "client": ("203.0.113.50", 1), "headers": []}
    for _ in range(5):
        start, _ = asyncio.run(_run(app, scope))
        assert start["status"] == 200


def test_middleware_agrega_cabeceras_de_seguridad():
    start, _ = asyncio.run(_run(_mw(), _post_scope(content_length=2), body=b"{}"))
    names = {k for k, _ in start["headers"]}
    assert {b"x-content-type-options", b"x-frame-options", b"cache-control"} <= names
