"""Gestionnaire d'embeddings texte et image  client HTTP vers le service
`pytorch_models` (port 8001), qui charge réellement sentence-transformers et
CLIP.

Choix d'architecture (décidé explicitement, pas par défaut) : plutôt que de
charger sentence-transformers/CLIP en local dans ce module  ce qui aurait
obligé à installer `requirements/ml.txt` (torch, transformers...) dans
l'image backend générale (langgraph_api, workers Celery), à rebours de la
séparation base/ml actée au Prompt 1.4  `embedding_manager.py` reste un
client HTTP léger (httpx, déjà dans `requirements/base.txt`). Seul
`pytorch_models` installe la stack ML (`backend/Dockerfile.ml`).

Contrat HTTP attendu côté `pytorch_models`  À IMPLÉMENTER, n'existe pas
encore. Ni ce prompt (2.3, couche mémoire) ni le Prompt 3.2 de
mise_en_place.md (qui ne couvre que POST /route pour le classifieur de
complexité) ne créent ces endpoints ; il faudra les ajouter à
`backend/pytorch_models/api/` avant que ce module fonctionne réellement :

- POST /embeddings/text        {"text": str}         -> {"vector": list[float]}          (768 dim)
- POST /embeddings/text-batch  {"texts": list[str]}   -> {"vectors": list[list[float]]}   (768 dim chacun)
- POST /embeddings/image       {"image_path": str}    -> {"vector": list[float]}          (512 dim, CLIP)
- POST /embeddings/text-clip   {"text": str}           -> {"vector": list[float]}          (512 dim, CLIP  espace image/texte partagé)
"""

import asyncio
import hashlib
import time
from typing import ClassVar

import httpx
import structlog

from backend.config.settings import settings
from backend.core.memory.redis_client import get_redis_client

logger = structlog.get_logger(__name__)

EMBEDDING_CACHE_TTL_SECONDS = 60 * 60  # 1h
_REQUEST_TIMEOUT_SECONDS = 30.0


class _PytorchModelsClient:
    """Client HTTP partagé (pooling de connexions) vers le service pytorch_models."""

    _client: ClassVar[httpx.AsyncClient | None] = None

    @classmethod
    def get(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                base_url=settings.PYTORCH_MODELS_URL, timeout=_REQUEST_TIMEOUT_SECONDS
            )
        return cls._client


class TextEmbedder:
    """Embeddings texte (768 dim, sentence-transformers côté pytorch_models),
    pour COLLECTION_CONTENTS, COLLECTION_BRAND_KNOWLEDGE, COLLECTION_CAMPAIGNS,
    COLLECTION_KEYWORDS, COLLECTION_AUDIENCES."""

    @staticmethod
    def _cache_key(text: str) -> str:
        return f"embedding:text:{hashlib.sha256(text.encode()).hexdigest()}"

    async def embed_text(self, text: str) -> list[float]:
        redis_client = get_redis_client()

        async def _compute() -> list[float]:
            start = time.perf_counter()
            response = await _PytorchModelsClient.get().post("/embeddings/text", json={"text": text})
            response.raise_for_status()
            vector = response.json()["vector"]
            latency_ms = (time.perf_counter() - start) * 1000
            # Métrique de latence : loggée en structuré, à relayer vers LangFuse
            # par l'appelant (même principe que routing_cache.get_cache_stats).
            logger.info("text_embedder.computed", latency_ms=latency_ms, text_length=len(text))
            return vector

        return await redis_client.get_or_set(
            self._cache_key(text), _compute, ttl=EMBEDDING_CACHE_TTL_SECONDS
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Version batch : réutilise le cache par texte individuel, et regroupe
        en un seul appel HTTP uniquement les textes non déjà en cache."""
        if not texts:
            return []

        redis_client = get_redis_client()
        keys = [self._cache_key(t) for t in texts]
        cached_values = await asyncio.gather(*(redis_client.get(k) for k in keys))

        results: list[list[float] | None] = list(cached_values)
        missing_indices = [i for i, v in enumerate(results) if v is None]

        if missing_indices:
            missing_texts = [texts[i] for i in missing_indices]
            start = time.perf_counter()
            response = await _PytorchModelsClient.get().post(
                "/embeddings/text-batch", json={"texts": missing_texts}
            )
            response.raise_for_status()
            vectors = response.json()["vectors"]
            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "text_embedder.batch_computed", latency_ms=latency_ms, count=len(missing_texts)
            )
            for idx, vector in zip(missing_indices, vectors):
                results[idx] = vector
                await redis_client.set(keys[idx], vector, ttl=EMBEDDING_CACHE_TTL_SECONDS)

        return results  # type: ignore[return-value]  # tous les éléments sont remplis à ce stade


class ImageEmbedder:
    """Embeddings CLIP (512 dim, côté pytorch_models), pour COLLECTION_VISUAL_REFERENCES.

    CLIP projette images ET texte dans le même espace vectoriel : en plus de
    `embed_image`, expose `embed_text_for_clip`  nécessaire pour rechercher
    des références visuelles à partir d'une description textuelle
    (semantic_search.search_visual_references). `TextEmbedder` ne convient
    PAS pour cet usage : ses vecteurs sont en 768 dim, un espace différent et
    incompatible avec les 512 dim stockées dans COLLECTION_VISUAL_REFERENCES.
    """

    async def embed_image(self, image_path: str) -> list[float]:
        cache_key = f"embedding:image:{hashlib.sha256(image_path.encode()).hexdigest()}"
        redis_client = get_redis_client()

        async def _compute() -> list[float]:
            start = time.perf_counter()
            response = await _PytorchModelsClient.get().post(
                "/embeddings/image", json={"image_path": image_path}
            )
            response.raise_for_status()
            vector = response.json()["vector"]
            latency_ms = (time.perf_counter() - start) * 1000
            logger.info("image_embedder.computed", latency_ms=latency_ms, image_path=image_path)
            return vector

        return await redis_client.get_or_set(cache_key, _compute, ttl=EMBEDDING_CACHE_TTL_SECONDS)

    async def embed_text_for_clip(self, text: str) -> list[float]:
        cache_key = f"embedding:clip_text:{hashlib.sha256(text.encode()).hexdigest()}"
        redis_client = get_redis_client()

        async def _compute() -> list[float]:
            start = time.perf_counter()
            response = await _PytorchModelsClient.get().post(
                "/embeddings/text-clip", json={"text": text}
            )
            response.raise_for_status()
            vector = response.json()["vector"]
            latency_ms = (time.perf_counter() - start) * 1000
            logger.info("image_embedder.text_computed", latency_ms=latency_ms, text_length=len(text))
            return vector

        return await redis_client.get_or_set(cache_key, _compute, ttl=EMBEDDING_CACHE_TTL_SECONDS)
