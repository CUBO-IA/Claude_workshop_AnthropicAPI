#!/usr/bin/env bash
# Genera el certificado TLS autofirmado para desarrollo local (válido 365 días).
# Salida: certs/cert.pem y certs/key.pem (ignorados por git).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/certs"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$ROOT/certs/key.pem" \
  -out "$ROOT/certs/cert.pem" \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

# Los contenedores leen la clave con un usuario no root (uid 10001).
# Solo para desarrollo local; en producción usar un certificado real y un secreto.
chmod 644 "$ROOT/certs/key.pem"
echo "Certificados generados en $ROOT/certs"
