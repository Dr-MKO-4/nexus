"""Définition et initialisation des collections Qdrant (mémoire sémantique).

Chaque collection est décrite par une `CollectionSpec` : la taille du vecteur,
la métrique de distance, et le schéma de payload attendu (documentaire 
Qdrant n'impose pas de schéma de payload strict, contrairement aux colonnes
d'une table SQL ; ce tuple sert de contrat pour les producteurs/consommateurs
de chaque collection, voir semantic_search.py).
"""

from dataclasses import dataclass

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CollectionSpec:
    name: str
    vector_size: int
    distance: Distance
    payload_schema: tuple[str, ...]


COLLECTION_CONTENTS = CollectionSpec(
    name="contents",
    vector_size=768,  # sentence-transformers (paraphrase-multilingual-mpnet-base-v2)
    distance=Distance.COSINE,
    payload_schema=(
        "content_id",
        "client_id",
        "content_type",
        "platform",
        "title",
        "created_at",
        "performance_score",
    ),
)

COLLECTION_BRAND_KNOWLEDGE = CollectionSpec(
    name="brand_knowledge",
    vector_size=768,
    distance=Distance.COSINE,
    payload_schema=("client_id", "knowledge_type", "text", "source"),
)

COLLECTION_CAMPAIGNS = CollectionSpec(
    name="campaigns",
    vector_size=768,
    distance=Distance.COSINE,
    payload_schema=("campaign_id", "client_id", "objective", "channels", "results_summary", "period"),
)

COLLECTION_KEYWORDS = CollectionSpec(
    name="keywords",
    vector_size=768,
    distance=Distance.COSINE,
    payload_schema=("client_id", "keyword", "cluster_name", "search_volume", "difficulty"),
)

COLLECTION_AUDIENCES = CollectionSpec(
    name="audiences",
    vector_size=768,
    distance=Distance.COSINE,
    payload_schema=("client_id", "segment_name", "behavior_pattern", "conversion_rate"),
)

COLLECTION_VISUAL_REFERENCES = CollectionSpec(
    name="visual_references",
    vector_size=512,  # CLIP (openai/clip-vit-base-patch32)  espace partagé image/texte
    distance=Distance.COSINE,
    payload_schema=("client_id", "visual_type", "style_tags", "file_path", "usage_count"),
)

ALL_COLLECTIONS: tuple[CollectionSpec, ...] = (
    COLLECTION_CONTENTS,
    COLLECTION_BRAND_KNOWLEDGE,
    COLLECTION_CAMPAIGNS,
    COLLECTION_KEYWORDS,
    COLLECTION_AUDIENCES,
    COLLECTION_VISUAL_REFERENCES,
)


async def initialize_collections(client: AsyncQdrantClient) -> None:
    """Crée toutes les collections listées dans ALL_COLLECTIONS si elles n'existent pas."""
    for spec in ALL_COLLECTIONS:
        exists = await client.collection_exists(spec.name)
        if exists:
            logger.debug("qdrant.collection_already_exists", collection=spec.name)
            continue

        await client.create_collection(
            collection_name=spec.name,
            vectors_config=VectorParams(size=spec.vector_size, distance=spec.distance),
        )
        logger.info(
            "qdrant.collection_created",
            collection=spec.name,
            vector_size=spec.vector_size,
            distance=spec.distance.value,
        )
