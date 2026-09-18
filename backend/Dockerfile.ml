# Image du service pytorch_models : sert les modèles internes (classification,
# embeddings, scoring, anomalies) via FastAPI, avec accès GPU.

FROM pytorch/pytorch:2.5.0-cuda12.1-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Restreint la visibilité des GPU pour ce conteneur ; surchargé par docker-compose
    # (deploy.resources.reservations.devices) selon les GPU réellement alloués.
    CUDA_VISIBLE_DEVICES=0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/ml.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/base.txt -r requirements/ml.txt

COPY . ./backend/

EXPOSE 8001

ENTRYPOINT ["uvicorn"]
CMD ["backend.pytorch_models.main:app", "--host", "0.0.0.0", "--port", "8001"]
