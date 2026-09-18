"""Mémoire court terme et long terme des agents (contexte de conversation, historique des décisions)."""

from backend.core.memory.collections import (
    ALL_COLLECTIONS,
    COLLECTION_AUDIENCES,
    COLLECTION_BRAND_KNOWLEDGE,
    COLLECTION_CAMPAIGNS,
    COLLECTION_CONTENTS,
    COLLECTION_KEYWORDS,
    COLLECTION_VISUAL_REFERENCES,
    CollectionSpec,
    initialize_collections,
)
from backend.core.memory.embedding_manager import ImageEmbedder, TextEmbedder
from backend.core.memory.qdrant_client import QdrantMemoryClient, get_qdrant_client
from backend.core.memory.redis_client import RedisClient, cache, get_redis_client
from backend.core.memory.routing_cache import RoutingCache, RoutingDecision
from backend.core.memory.semantic_search import (
    CampaignSearchResult,
    ContentSearchResult,
    KnowledgeSearchResult,
    VisualSearchResult,
    search_brand_knowledge,
    search_past_campaigns,
    search_similar_contents,
    search_visual_references,
    upsert_content,
    upsert_visual,
)
from backend.core.memory.session_manager import SessionData, SessionManager

__all__ = [
    # Redis
    "RedisClient",
    "get_redis_client",
    "cache",
    "SessionManager",
    "SessionData",
    "RoutingCache",
    "RoutingDecision",
    # Qdrant
    "QdrantMemoryClient",
    "get_qdrant_client",
    "CollectionSpec",
    "ALL_COLLECTIONS",
    "COLLECTION_CONTENTS",
    "COLLECTION_BRAND_KNOWLEDGE",
    "COLLECTION_CAMPAIGNS",
    "COLLECTION_KEYWORDS",
    "COLLECTION_AUDIENCES",
    "COLLECTION_VISUAL_REFERENCES",
    "initialize_collections",
    # Embeddings
    "TextEmbedder",
    "ImageEmbedder",
    # Recherche sémantique
    "search_similar_contents",
    "search_brand_knowledge",
    "search_visual_references",
    "search_past_campaigns",
    "upsert_content",
    "upsert_visual",
    "ContentSearchResult",
    "KnowledgeSearchResult",
    "VisualSearchResult",
    "CampaignSearchResult",
]
