# Image de production pour l'API LangGraph, les workers Celery et Celery Beat.
# Multi-stage : les outils de compilation restent dans le stage builder et
# n'alourdissent pas l'image finale.

# ---------- Stage 1 : builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt ./requirements/base.txt

# Installées dans un préfixe dédié pour être copiées telles quelles dans le stage final
RUN pip install --no-cache-dir --prefix=/install -r requirements/base.txt

# ---------- Stage 2 : production ----------
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:$PATH

WORKDIR /app

# libpq5 : dépendance runtime de psycopg2 (pas besoin de libpq-dev ni de build-essential ici)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 nexus \
    && useradd --uid 1000 --gid nexus --shell /bin/bash --create-home nexus

COPY --from=builder /install /usr/local
COPY --chown=nexus:nexus . ./backend/

USER nexus

EXPOSE 8000

ENTRYPOINT ["uvicorn"]
CMD ["backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
