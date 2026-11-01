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
docker compose up -d mongodb
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

## Seguridad y limitaciones conocidas

- **HTTPS:** frontend y backend usan TLS con certificado autofirmado (solo desarrollo). En producción conviene un certificado de una CA y un proxy único.
- **MongoDB:** la conexión entre contenedores es TCP sin TLS, y el puerto del host solo escucha en `127.0.0.1`. Para cumplir "todo HTTPS" habría que activar TLS en MongoDB.
- **Permisos de la clave:** `certs/key.pem` tiene permisos 644 para que el usuario del contenedor pueda leerla. Es aceptable solo en local.
- **Temperatura 0:** no es posible con los modelos Claude 5. La consistencia se logra limitando la elección a candidatos recuperados.
- **Credenciales:** `.env` contiene secretos y está excluido de git. No lo compartas.
