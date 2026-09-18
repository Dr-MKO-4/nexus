"""Interface de recherche sémantique de haut niveau, au-dessus de Qdrant.

Toutes les recherches filtrent sur `client_id` (isolation multi-tenant) :
un client ne doit jamais voir les contenus, connaissances ou campagnes d'un
autre client via une similarité sémantique fortuite.
"""

import uuid
from typing import Any

import structlog
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, MatchValue

from backend.core.memory.collections import (
    COLLECTION_BRAND_KNOWLEDGE,
    COLLECTION_CAMPAIGNS,
    COLLECTION_CONTENTS,
    COLLECTION_VISUAL_REFERENCES,
)
from backend.core.memory.embedding_manager import ImageEmbedder, TextEmbedder
from backend.core.memory.qdrant_client import QdrantMemoryClient, get_qdrant_client

logger = structlog.get_logger(__name__)


# ----------------------------------------------------------------------------
# Résultats de recherche  projections légères du payload Qdrant, distinctes
# des modèles ORM (backend.db.models) : une recherche vectorielle ne renvoie
# qu'un point_id/score/payload, jamais une entité relationnelle complète.
# ----------------------------------------------------------------------------


class ContentSearchResult(BaseModel):
    point_id: str
    score: float
    content_id: str | None = None
    client_id: str | None = None
    content_type: str | None = None
    platform: str | None = None
    title: str | None = None
    created_at: str | None = None
    performance_score: float | None = None


class KnowledgeSearchResult(BaseModel):
    point_id: str
    score: float
    client_id: str | None = None
    knowledge_type: str | None = None
    text: str | None = None
    source: str | None = None


class VisualSearchResult(BaseModel):
    point_id: str
    score: float
    client_id: str | None = None
    visual_type: str | None = None
    style_tags: list[str] | None = None
    file_path: str | None = None
    usage_count: int | None = None


class CampaignSearchResult(BaseModel):
    point_id: str
    score: float
    campaign_id: str | None = None
    client_id: str | None = None
    objective: str | None = None
    channels: list[str] | None = None
    results_summary: str | None = None
    period: str | None = None


def _client_filter(client_id: str) -> Filter:
    return Filter(must=[FieldCondition(key="client_id", match=MatchValue(value=client_id))])


def _to_result(model_cls: type[BaseModel], hit: dict[str, Any]) -> BaseModel:
    payload = hit.get("payload") or {}
    return model_cls(point_id=str(hit["id"]), score=hit["score"], **payload)


# ----------------------------------------------------------------------------
# Recherche
# ----------------------------------------------------------------------------


async def search_similar_contents(
    text: str, client_id: str, limit: int = 5, *, qdrant: QdrantMemoryClient | None = None
) -> list[ContentSearchResult]:
    client = qdrant or get_qdrant_client()
    vector = await TextEmbedder().embed_text(text)
    hits = await client.search(
        COLLECTION_CONTENTS.name, vector, limit=limit, query_filter=_client_filter(client_id)
    )
    logger.debug("semantic_search.similar_contents", client_id=client_id, hits=len(hits))
    return [_to_result(ContentSearchResult, h) for h in hits]  # type: ignore[misc]


async def search_brand_knowledge(
    query: str, client_id: str, limit: int = 3, *, qdrant: QdrantMemoryClient | None = None
) -> list[KnowledgeSearchResult]:
    client = qdrant or get_qdrant_client()
    vector = await TextEmbedder().embed_text(query)
    hits = await client.search(
        COLLECTION_BRAND_KNOWLEDGE.name, vector, limit=limit, query_filter=_client_filter(client_id)
    )
    logger.debug("semantic_search.brand_knowledge", client_id=client_id, hits=len(hits))
    return [_to_result(KnowledgeSearchResult, h) for h in hits]  # type: ignore[misc]


async def search_visual_references(
    brief_text: str, client_id: str, limit: int = 5, *, qdrant: QdrantMemoryClient | None = None
) -> list[VisualSearchResult]:
    client = qdrant or get_qdrant_client()
    # CLIP, pas TextEmbedder : COLLECTION_VISUAL_REFERENCES stocke des vecteurs
    # CLIP 512 dim, incompatibles avec les 768 dim de sentence-transformers.
    vector = await ImageEmbedder().embed_text_for_clip(brief_text)
    hits = await client.search(
        COLLECTION_VISUAL_REFERENCES.name, vector, limit=limit, query_filter=_client_filter(client_id)
    )
    logger.debug("semantic_search.visual_references", client_id=client_id, hits=len(hits))
    return [_to_result(VisualSearchResult, h) for h in hits]  # type: ignore[misc]


async def search_past_campaigns(
    objective: str, client_id: str, limit: int = 3, *, qdrant: QdrantMemoryClient | None = None
) -> list[CampaignSearchResult]:
    client = qdrant or get_qdrant_client()
    vector = await TextEmbedder().embed_text(objective)
    hits = await client.search(
        COLLECTION_CAMPAIGNS.name, vector, limit=limit, query_filter=_client_filter(client_id)
    )
    logger.debug("semantic_search.past_campaigns", client_id=client_id, hits=len(hits))
    return [_to_result(CampaignSearchResult, h) for h in hits]  # type: ignore[misc]


# ----------------------------------------------------------------------------
# Upsert
# ----------------------------------------------------------------------------


async def upsert_content(
    content: dict[str, Any], client_id: str, *, qdrant: QdrantMemoryClient | None = None
) -> str:
    """`content` doit fournir le texte à vectoriser sous la clé "text" (ou "title"
    à défaut), plus les champs du payload_schema de COLLECTION_CONTENTS."""
    client = qdrant or get_qdrant_client()
    text = content.get("text") or content.get("title") or ""
    vector = await TextEmbedder().embed_text(text)

    point_id = str(content.get("content_id") or uuid.uuid4())
    payload = {
        "content_id": point_id,
        "client_id": client_id,
        "content_type": content.get("content_type"),
        "platform": content.get("platform"),
        "title": content.get("title"),
        "created_at": content.get("created_at"),
        "performance_score": content.get("performance_score"),
    }
    await client.upsert(COLLECTION_CONTENTS.name, point_id, vector, payload)
    logger.info("semantic_search.content_upserted", point_id=point_id, client_id=client_id)
    return point_id


async def upsert_visual(
    image_path: str,
    metadata: dict[str, Any],
    client_id: str,
    *,
    qdrant: QdrantMemoryClient | None = None,
) -> str:
    client = qdrant or get_qdrant_client()
    vector = await ImageEmbedder().embed_image(image_path)

    point_id = str(metadata.get("visual_id") or uuid.uuid4())
    payload = {
        "client_id": client_id,
        "visual_type": metadata.get("visual_type"),
        "style_tags": metadata.get("style_tags"),
        "file_path": image_path,
        "usage_count": metadata.get("usage_count", 0),
    }
    await client.upsert(COLLECTION_VISUAL_REFERENCES.name, point_id, vector, payload)
    logger.info("semantic_search.visual_upserted", point_id=point_id, client_id=client_id)
    return point_id
