"""Chargeur et validateur de la ligne éditoriale d'un client  Prompt 5.3.

Structure canonique (ton, style, contraintes) depuis PostgreSQL
(`Client.editorial_guidelines`, `Client.forbidden_topics`, Prompt 1.3),
enrichie des extraits de connaissance de marque les plus proches
sémantiquement dans Qdrant (COLLECTION_BRAND_KNOWLEDGE, via
`semantic_search.search_brand_knowledge`, Prompt 2.3)  la table SQL porte la
structure, Qdrant apporte le contexte de marque en langage libre.
"""

from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
_SIMILAR_KNOWLEDGE_LIMIT = 5


class EditorialGuidelines(BaseModel):
    model_config = _STRICT_CONFIG

    client_id: str
    tone: str | None = None
    style: str | None = None
    forbidden_topics: list[str] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    brand_knowledge_snippets: list[str] = Field(
        default_factory=list, description="Extraits de connaissance de marque les plus proches (Qdrant)."
    )


class Violation(BaseModel):
    model_config = _STRICT_CONFIG

    rule: str
    severity: Literal["warning", "critical"]
    message: str


async def load_guidelines(client_id: str) -> EditorialGuidelines:
    structure: dict = {}
    forbidden_topics: list[str] = []
    try:
        from backend.db.repositories.client_repository import ClientRepository
        from backend.db.session import get_session

        async with get_session() as session:
            client = await ClientRepository(session).get_by_id(UUID(client_id))
        if client is not None:
            structure = client.editorial_guidelines or {}
            forbidden_topics = client.forbidden_topics or []
    except Exception as exc:
        logger.warning("editorial_guidelines.postgres_load_failed", client_id=client_id, error=str(exc))

    snippets: list[str] = []
    try:
        from backend.core.memory.semantic_search import search_brand_knowledge

        query_text = " ".join(filter(None, [structure.get("tone"), structure.get("style")])) or "ligne éditoriale"
        results = await search_brand_knowledge(query_text, client_id, limit=_SIMILAR_KNOWLEDGE_LIMIT)
        snippets = [r.text for r in results if r.text]
    except Exception as exc:
        logger.warning("editorial_guidelines.qdrant_search_failed", client_id=client_id, error=str(exc))

    logger.info("editorial_guidelines.loaded", client_id=client_id, snippet_count=len(snippets))
    return EditorialGuidelines(
        client_id=client_id,
        tone=structure.get("tone"),
        style=structure.get("style"),
        forbidden_topics=forbidden_topics,
        constraints=structure.get("constraints", {}),
        brand_knowledge_snippets=snippets,
    )


def validate_content_against_guidelines(content: str, guidelines: EditorialGuidelines) -> list[Violation]:
    violations: list[Violation] = []
    lowered = content.lower()

    for topic in guidelines.forbidden_topics:
        if topic and topic.lower() in lowered:
            violations.append(
                Violation(
                    rule="forbidden_topic",
                    severity="critical",
                    message=f"Le contenu mentionne un sujet interdit : {topic!r}.",
                )
            )

    word_count = len(content.split())
    max_length = guidelines.constraints.get("max_length_words")
    if max_length and word_count > max_length:
        violations.append(
            Violation(
                rule="max_length",
                severity="warning",
                message=f"Contenu de {word_count} mots, au-delà de la limite de {max_length}.",
            )
        )

    min_length = guidelines.constraints.get("min_length_words")
    if min_length and word_count < min_length:
        violations.append(
            Violation(
                rule="min_length",
                severity="warning",
                message=f"Contenu de {word_count} mots, en dessous du minimum de {min_length}.",
            )
        )

    required_terms = guidelines.constraints.get("required_terms") or []
    for term in required_terms:
        if term and term.lower() not in lowered:
            violations.append(
                Violation(
                    rule="required_term",
                    severity="warning",
                    message=f"Le terme requis {term!r} est absent du contenu.",
                )
            )

    return violations


__all__ = ["EditorialGuidelines", "Violation", "load_guidelines", "validate_content_against_guidelines"]
