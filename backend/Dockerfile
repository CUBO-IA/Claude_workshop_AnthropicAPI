FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/backend

COPY requirements.txt .
RUN pip install -r requirements.txt

# Modelo de embeddings horneado en la imagen (el contenedor tiene el sistema de archivos de solo lectura).
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-large
ENV FASTEMBED_CACHE_PATH=/opt/models \
    EMBEDDING_MODEL=${EMBEDDING_MODEL}
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding(model_name=os.environ['EMBEDDING_MODEL'], cache_dir=os.environ['FASTEMBED_CACHE_PATH'])" \
    && chmod -R a+rX /opt/models

COPY app ./app

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8443

# HTTPS con certificado montado en /certs (autofirmado en desarrollo)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/certs/key.pem", "--ssl-certfile", "/certs/cert.pem"]
