"""Implémentation des nœuds de l'Agent SEO."""

import json
from uuid import UUID

import structlog
from pydantic import BaseModel

from backend.agents.seo.prompts import get_seo_prompt
from backend.agents.seo.state import SEOState
from backend.core.state.state_models import Keyword
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.llm.gateway.structured_output import parse_llm_json
from backend.tools.seo.keyword_research import analyze_keyword_intent, cluster_keywords, estimate_difficulty, search_keywords
from backend.tools.seo.technical_audit import audit_page_speed, check_meta_tags, check_mobile_friendly, check_structured_data

logger = structlog.get_logger(__name__)


class _SelectedKeyword(BaseModel):
    term: str
    reasoning: str


class _KeywordSelection(BaseModel):
    """Sortie structurée de research_keywords_node  via instructor/Pydantic
    (NexusLLMClient.complete_structured), pas un parsing JSON manuel, comme
    l'exige le Prompt 5.1."""

    selected_keywords: list[_SelectedKeyword]


class ContentBrief(BaseModel):
    """Sortie structurée de generate_briefs_node  mêmes champs que
    demandés par le Prompt 5.1 (titre, structure, mots-clés cibles,
    longueur, angle éditorial)."""

    title: str
    structure: list[str]
    target_keywords: list[str]
    target_length_words: int
    editorial_angle: str


async def load_seo_context_node(state: SEOState) -> dict:
    """Charge l'historique SEO (PostgreSQL : mots-clés déjà suivis, site du
    client) et les connaissances de marque pertinentes (Qdrant)."""
    client_id = state["client_id"]
    existing_keywords: list[Keyword] = []
    site_url: str | None = None
    industry: str | None = None

    try:
        from backend.db.repositories.client_repository import ClientRepository
        from backend.db.repositories.keyword_repository import KeywordRepository
        from backend.db.session import get_session

        async with get_session() as session:
            db_keywords = await KeywordRepository(session).get_by_client(UUID(client_id))
            client = await ClientRepository(session).get_by_id(UUID(client_id))

        existing_keywords = [
            Keyword(
                term=k.term,
                volume=k.search_volume,
                difficulty=k.difficulty,
                position=k.current_position,
                cluster=(k.cluster or {}).get("cluster_name") if k.cluster else None,
            )
            for k in db_keywords
        ]
        if client:
            site_url = client.website
            industry = client.industry
    except Exception as exc:
        logger.warning("seo_nodes.load_context_db_failed", client_id=client_id, error=str(exc))

    editorial_context: str | None = None
    try:
        from backend.core.memory.semantic_search import search_brand_knowledge

        objective = (state.get("brief") or {}).get("objective", "")
        knowledge = await search_brand_knowledge(objective, client_id, limit=3) if objective else []
        editorial_context = " | ".join(k.text for k in knowledge if k.text) or None
    except Exception as exc:
        logger.warning("seo_nodes.load_context_qdrant_failed", client_id=client_id, error=str(exc))

    logger.info(
        "seo_nodes.context_loaded",
        client_id=client_id,
        existing_keyword_count=len(existing_keywords),
        site_url=site_url,
    )
    return {
        "existing_keywords": existing_keywords,
        "site_url": site_url,
        "industry": industry,
        "editorial_context": editorial_context,
    }


async def research_keywords_node(state: SEOState) -> dict:
    """Recherche de candidats (Serper/SearXNG) puis sélection par LLM
    (Mistral 7B  task_type="seo_analysis", voir hybrid_router.py)."""
    brief = state.get("brief") or {}
    objective = brief.get("objective", "")
    existing_terms = {k.term.lower() for k in (state.get("existing_keywords") or [])}

    candidates: list[dict] = []
    seed_terms = [objective] if objective else ["marketing digital"]
    for term in seed_terms:
        try:
            results = await search_keywords(term)
        except Exception as exc:
            logger.warning("seo_nodes.keyword_search_failed", term=term, error=str(exc))
            continue
        for result in results:
            for candidate_term in {result.term, *result.related_terms}:
                if candidate_term.lower() in existing_terms:
                    continue
                candidates.append(
                    {
                        "term": candidate_term,
                        "intent": analyze_keyword_intent(candidate_term),
                        "difficulty": estimate_difficulty(candidate_term),
                    }
                )

    llm_client = NexusLLMClient()
    prompt = get_seo_prompt(
        "seo-keyword-research",
        objective=objective,
        industry=state.get("industry") or "non précisé",
        existing_keywords=", ".join(sorted(existing_terms)) or "aucun",
        keyword_candidates=json.dumps(candidates[:50], ensure_ascii=False),
    )
    try:
        selection = await llm_client.complete_structured(
            prompt=prompt,
            response_model=_KeywordSelection,
            task_type="seo_analysis",
            client_id=state["client_id"],
            agent_name="seo",
        )
        selected_keywords = [Keyword(term=item.term) for item in selection.selected_keywords]
    except Exception as exc:
        logger.warning("seo_nodes.structured_output_failed", node="research_keywords", error=str(exc))
        selected_keywords = []

    logger.info(
        "seo_nodes.keywords_researched",
        client_id=state["client_id"],
        candidate_count=len(candidates),
        selected_count=len(selected_keywords),
    )
    return {"keyword_candidates": candidates, "seo_keywords": selected_keywords}


async def audit_technical_node(state: SEOState) -> dict:
    """Audit technique du site client  sauté si aucun site_url n'a pu être
    résolu (client sans website renseigné)."""
    site_url = state.get("site_url")
    if not site_url:
        logger.info("seo_nodes.audit_skipped_no_site_url", client_id=state["client_id"])
        return {"seo_audit_results": None}

    try:
        speed = await audit_page_speed(site_url)
        meta = await check_meta_tags(site_url)
        structured = await check_structured_data(site_url)
        mobile_friendly = await check_mobile_friendly(site_url)
        results = {
            "performance_score": speed.performance_score,
            "title": meta.title,
            "title_length": meta.title_length,
            "has_canonical": meta.has_canonical,
            "has_structured_data": structured.has_structured_data,
            "schema_types_found": structured.schema_types_found,
            "mobile_friendly": mobile_friendly,
        }
    except Exception as exc:
        logger.warning("seo_nodes.audit_failed", site_url=site_url, error=str(exc))
        results = {"error": str(exc)}

    logger.info("seo_nodes.audit_completed", site_url=site_url)
    return {"seo_audit_results": results}


async def analyze_competitors_node(state: SEOState) -> dict:
    """Analyse SERP des concurrents pour le premier mot-clé sélectionné 
    volontairement limité à un seul mot-clé représentatif (analyser toute la
    liste multiplierait les appels SearXNG/Serper sans bénéfice proportionnel
    pour un simple diagnostic de positionnement concurrentiel)."""
    keywords = state.get("seo_keywords") or []
    if not keywords:
        return {"competitor_analysis": None}

    keyword = keywords[0].term
    try:
        results = await search_keywords(keyword)
        serp_summary = [{"term": r.term, "related": r.related_terms[:5]} for r in results]
    except Exception as exc:
        logger.warning("seo_nodes.competitor_search_failed", keyword=keyword, error=str(exc))
        return {"competitor_analysis": None}

    llm_client = NexusLLMClient()
    prompt = get_seo_prompt(
        "seo-competitor-analysis", keyword=keyword, serp_results=json.dumps(serp_summary, ensure_ascii=False)
    )
    raw_response = await llm_client.complete(
        prompt=prompt, task_type="seo_analysis", client_id=state["client_id"], agent_name="seo"
    )
    parsed, error = parse_llm_json(raw_response, source="seo.analyze_competitors")

    logger.info("seo_nodes.competitors_analyzed", keyword=keyword, parse_error=error)
    return {"competitor_analysis": parsed if not error else None}


async def generate_briefs_node(state: SEOState) -> dict:
    """Génère un brief de contenu SEO complet par mot-clé sélectionné, à
    destination de l'Agent Content."""
    keywords = state.get("seo_keywords") or []
    clusters = cluster_keywords([k.term for k in keywords])
    llm_client = NexusLLMClient()

    briefs: list[dict] = []
    for keyword in keywords:
        cluster_terms = next((terms for terms in clusters.values() if keyword.term in terms), [keyword.term])
        prompt = get_seo_prompt(
            "seo-brief-generation",
            keyword=keyword.term,
            cluster_keywords=", ".join(t for t in cluster_terms if t != keyword.term) or "aucun",
            intent=analyze_keyword_intent(keyword.term),
            editorial_guidelines=state.get("editorial_context") or "non renseignées",
        )
        try:
            brief = await llm_client.complete_structured(
                prompt=prompt,
                response_model=ContentBrief,
                task_type="seo_analysis",
                client_id=state["client_id"],
                agent_name="seo",
            )
            briefs.append({"keyword": keyword.term, **brief.model_dump()})
        except Exception as exc:
            logger.warning("seo_nodes.structured_output_failed", node="generate_briefs", keyword=keyword.term, error=str(exc))

    logger.info("seo_nodes.briefs_generated", client_id=state["client_id"], brief_count=len(briefs))
    return {"content_briefs": briefs}


async def update_seo_memory_node(state: SEOState) -> dict:
    """Met à jour Qdrant (COLLECTION_KEYWORDS via l'espace générique
    sémantique) avec les nouveaux mots-clés identifiés, pour que les
    prochaines recherches sémantiques (Agent Content, prochains cycles SEO)
    en bénéficient."""
    keywords = state.get("seo_keywords") or []
    if not keywords:
        return {}

    try:
        from backend.core.memory.collections import COLLECTION_KEYWORDS
        from backend.core.memory.embedding_manager import TextEmbedder
        from backend.core.memory.qdrant_client import get_qdrant_client

        embedder = TextEmbedder()
        qdrant = get_qdrant_client()
        for keyword in keywords:
            vector = await embedder.embed_text(keyword.term)
            await qdrant.upsert(
                COLLECTION_KEYWORDS.name,
                point_id=f"{state['client_id']}:{keyword.term}",
                vector=vector,
                payload={"client_id": state["client_id"], "keyword": keyword.term, "cluster_name": keyword.cluster},
            )
        logger.info("seo_nodes.memory_updated", client_id=state["client_id"], keyword_count=len(keywords))
    except Exception as exc:
        logger.warning("seo_nodes.memory_update_failed", client_id=state["client_id"], error=str(exc))

    return {}


async def seo_reporter_node(state: SEOState) -> dict:
    """Compile et retourne les résultats  les champs seo_keywords/
    seo_audit_results sont déjà dans l'état, ce nœud ne fait que consigner
    la fin de l'exécution de l'agent."""
    logger.info(
        "seo_nodes.completed",
        client_id=state["client_id"],
        keyword_count=len(state.get("seo_keywords") or []),
        brief_count=len(state.get("content_briefs") or []),
    )
    return {}
