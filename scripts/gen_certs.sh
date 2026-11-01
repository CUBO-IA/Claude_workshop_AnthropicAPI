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

# Certificado del proxy TLS de MongoDB (contenedor fmc130-mongo-tls).
# Se genera solo si no existe, para no invalidar la confianza del resto de servicios.
# Los SAN cubren el nombre de servicio, la IP fija en la red de compose y el host local.
if [[ ! -f "$ROOT/certs/mongo-cert.pem" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$ROOT/certs/mongo-key.pem" \
    -out "$ROOT/certs/mongo-cert.pem" \
    -days 365 \
    -subj "/CN=fmc130-mongodb" \
    -addext "subjectAltName=DNS:fmc130-mongodb,DNS:mongodb,DNS:localhost,IP:172.30.0.5,IP:127.0.0.1"
  chmod 644 "$ROOT/certs/mongo-key.pem"
  echo "Certificado de MongoDB generado en $ROOT/certs/mongo-cert.pem"
else
  echo "Certificado de MongoDB ya existe; no se regenera."
fi
