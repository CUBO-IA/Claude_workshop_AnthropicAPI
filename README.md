# Soporte FMC130 – Chatbot RAG

Chat de soporte para configurar parámetros del **Teltonika FMC130**. Responde en español con el formato
`ParameterID: X Value: Y`, usando como fuente de verdad la
[wiki oficial de Teltonika](https://wiki.teltonika-gps.com/view/FMC130_Parameter_list)
(22 temas, 41 tablas).

Prueba de concepto para entorno local.

## Arquitectura

```
Navegador ──HTTPS──► frontend (nginx :4443)
                       │  /api/ → HTTPS
                       ▼
                    backend (FastAPI :8453 en host, HTTPS interno)
                       │
          ┌────────────┼─────────────────────┐
          ▼            ▼                     ▼
   OpenRouter     MongoDB Atlas local    Anthropic API
   (embeddings    (búsqueda vectorial)   (selección del
   nemotron-3.5)  fmc130_rag.parameters   candidato, Haiku)
```

- **Extracción** (`scripts/extract_fmc130.py`): descarga las 41 tablas de la wiki → `data/fmc130_parameters.json`.
- **Traducción** (`scripts/translate_fmc130.py`): nombres en inglés → español con Claude Haiku. Se cachea en `data/translations_es.json`.
- **Carga** (`scripts/load_mongo.py`): inserta los documentos en MongoDB (idempotente).
- **Embeddings** (`scripts/embed_mongo.py`): calcula vectores (2048 dimensiones) y crea el índice `parameters_vector_index`.
- **Backend** (`backend/app/`): embedding de la pregunta → top 8 candidatos → Claude elige uno → el código arma la respuesta.

Claude solo elige un número de candidato; el formato lo genera el código. Los modelos Claude 5
rechazan el parámetro `temperature`, así que no se envía.

## Requisitos

- Docker y Docker Compose
- Python 3.12+ (para los scripts de datos y las pruebas)
- Claves de API: Anthropic y OpenRouter (API key normal, no Management key)

## Puesta en marcha

```bash
# 1. Variables de entorno
cp .env.example .env
#    Completa ANTHROPIC_API_KEY, OPENROUTER_API_KEY y MONGODB_ROOT_PASSWORD.

# 2. Certificado TLS autofirmado (desarrollo)
scripts/gen_certs.sh

# 3. Entorno Python para los scripts de datos y las pruebas
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest

# 4. Base de datos (datos ya generados en data/; regenerar solo si cambia la wiki)
docker compose up -d mongodb mongo-tls
.venv/bin/python scripts/extract_fmc130.py     # opcional: regenera data/
.venv/bin/python scripts/translate_fmc130.py   # opcional: usa caché si existe
.venv/bin/python scripts/load_mongo.py
.venv/bin/python scripts/embed_mongo.py

# 5. Servicios
docker compose up -d --build backend frontend
```

Abre **https://127.0.0.1:4443** y acepta la advertencia del certificado autofirmado.

Para la API directamente: `https://127.0.0.1:8453/api/health` y `POST /api/chat` con `{"question": "..."}`.

## Pruebas

```bash
# Unitarias (sin red)
.venv/bin/python -m pytest tests/test_rag_unit.py -v

# Aceptación contra el servicio levantado
.venv/bin/python -m pytest tests/test_acceptance.py -v
```

Los criterios de aceptación propuestos están documentados en `tests/test_acceptance.py`:
formato exacto, respuestas esperadas, conjuntos válidos para preguntas ambiguas,
rechazo de preguntas fuera de dominio y consistencia entre ejecuciones.

## Estructura

```
backend/        API FastAPI (app/rag.py, app/main.py) y Dockerfile
frontend/       React + Vite + TypeScript, nginx como servidor HTTPS
scripts/        Pipeline de datos y utilidades (extracción, traducción, carga, embeddings, certificados)
data/           Parámetros extraídos y traducciones
tests/          Pruebas unitarias y de aceptación
certs/          Certificados TLS (no versionados)
docker-compose.yml
```

## Seguridad

Controles implementados:

| Área | Control |
|---|---|
| Rate limiting | 100 peticiones/minuto por IP en `POST /api/chat` (ventana deslizante). Responde 429 con `Retry-After`. Configurable con `RATE_LIMIT_PER_MINUTE`. |
| IP de cliente | Solo el proxy del frontend (IP fija `172.30.0.10`) puede fijar `X-Real-IP`. Un cliente no puede falsificar su IP. |
| Tamaño | Cuerpo máximo de 2 KB en el backend y de 2 KB en nginx. Pregunta de 3 a 500 caracteres, sin caracteres de control, campos extra rechazados. |
| Errores | Al cliente solo llegan mensajes genéricos. Los detalles van al log del servidor. |
| Documentación API | `/docs` y `/openapi.json` desactivados (`ENABLE_DOCS=false`). |
| Alcance | Preguntas fuera del FMC130 (identidad, clima, recetas, etc.) se rechazan. La pregunta se delimita en el prompt para evitar inyección. |
| Cabeceras | CSP estricta (`script-src 'self'`, `frame-ancestors 'none'`), HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`. |
| Métodos | nginx solo permite GET/HEAD en estáticos, POST en `/api/chat`, GET en `/api/health`. |
| Contenedores | Sistema de archivos de solo lectura, `cap_drop: ALL`, `no-new-privileges`, frontend sin root, red interna con IPs fijas. |
| Frontend | Sin `dangerouslySetInnerHTML` ni `eval`. Build con lockfile; `npm audit`: 0 vulnerabilidades. |

Prueba del límite (en vivo): 105 peticiones seguidas dan 100 respuestas válidas y 429 desde la 101.
Las pruebas de aceptación respetan `Retry-After`.

**Límites del modelo de amenaza**

- **El navegador no se puede blindar.** Quien controle su propio navegador puede modificar el JavaScript
  que recibe. Por eso el backend aplica todas las reglas (límites, alcance, formato): alterar el frontend
  no permite saltárselas. La CSP impide que código inyectado cargue scripts externos.
- **Autenticación:** no hay login (requisito del proyecto). Cualquiera con acceso a la red puede consultar, con el límite por IP.
- **Cuota de APIs:** el límite por IP no protege la cuota compartida de OpenRouter y Anthropic si muchas IPs consultan a la vez.

**Limitaciones conocidas**

- **MongoDB: TLS en el proxy, no en `mongod`.** La imagen Atlas Local no admite opciones TLS en `mongod`. El contenedor `mongo-tls` (nginx `stream`) termina TLS en el puerto 27443 y reenvía a `127.0.0.1:27017` dentro de la misma pila de red. El backend valida el certificado con `tlsCAFile`. El tramo proxy → `mongod` sigue sin cifrar, pero solo dentro del contenedor de MongoDB.
- **Replica set:** el `hostname` de `mongodb` está fijado (`8675e82b6b88`) porque el replica set guarda ese host. Si se cambia, hay que reconfigurar el replica set.
- **HTTPS con certificado autofirmado** (solo desarrollo). En producción, certificado de CA y secretos fuera de `.env`.
- **Permisos de la clave:** `certs/key.pem` tiene permisos 644 para que el usuario del contenedor pueda leerla.
- **Temperatura 0:** no es posible con los modelos Claude 5. La consistencia se logra con la caché de respuestas y el prompt delimitado.
- **Límite en memoria:** con varios procesos del backend, el contador no se comparte. Usar Redis si se escala.
- **Credenciales:** `.env` contiene secretos y está excluido de git. La aplicación usa el usuario root de MongoDB; en producción conviene un usuario con permisos mínimos.
