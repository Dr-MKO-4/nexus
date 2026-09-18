"""Implémentation des nœuds de l'Agent Content.

Génération avec Qwen3.5 72B (task_type="content_generation", voir
hybrid_router.TASK_TYPE_TO_LOCAL_MODEL) via `NexusLLMClient.complete_structured`
(instructor/Pydantic), cohérent avec le choix déjà fait pour les Agents SEO/SEA.
"""

import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.agents.content.prompts import get_content_prompt
from backend.agents.content.state import DEFAULT_MAX_ITERATIONS, ContentState
from backend.core.state.state_models import Content
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.pytorch_models.scoring.content_scorer import ContentScore, ContentScorer
from backend.tools.content.editorial_guidelines import EditorialGuidelines, load_guidelines

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

_QUALITY_THRESHOLD = 0.8

_PLATFORM_CONSTRAINTS = {
    "linkedin": "3000 caractères max, ton professionnel, format article si contenu long",
    "meta": "2200 caractères max, jusqu'à 30 hashtags",
    "tiktok": "script vidéo court, accroche dès les 3 premières secondes",
    "email": "pas de contrainte de longueur stricte, structure email",
    "web": "pas de contrainte de longueur stricte",
}

# Structure par défaut quand aucun ContentTemplate client n'existe en base
# (backend.tools.content n'a pas de générateur de structure dédié  ces
# structures par défaut sont un choix raisonnable documenté, pas une donnée
# inventée silencieusement).
_DEFAULT_STRUCTURES: dict[str, list[str]] = {
    "article": ["introduction", "développement", "conclusion", "appel à l'action"],
    "post": ["accroche", "message", "appel à l'action"],
    "email": ["objet", "accroche", "corps", "appel à l'action"],
    "landing_page": ["accroche", "bénéfices", "preuve sociale", "appel à l'action"],
}


class ContentDraft(BaseModel):
    model_config = _STRICT_CONFIG

    title: str
    body: str
    meta_description: str
    hashtags: list[str] = Field(default_factory=list)


class QualityJudgment(BaseModel):
    model_config = _STRICT_CONFIG

    score: float = Field(ge=0, le=1)
    feedback: str
    tone_ok: bool
    relevance_ok: bool


_scorer: ContentScorer | None = None


def _get_content_scorer() -> ContentScorer:
    global _scorer
    if _scorer is None:
        _scorer = ContentScorer.from_checkpoint()
    return _scorer


async def load_content_context_node(state: ContentState) -> dict:
    """Charge la ligne éditoriale (Qdrant + PostgreSQL, voir
    tools.content.editorial_guidelines) et vérifie les contenus similaires
    déjà produits pour ce client (Qdrant, COLLECTION_CONTENTS)."""
    client_id = state["client_id"]
    brief = state.get("brief") or {}

    guidelines = EditorialGuidelines(client_id=client_id)
    try:
        guidelines = await load_guidelines(client_id)
    except Exception as exc:
        logger.warning("content_nodes.guidelines_load_failed", client_id=client_id, error=str(exc))

    similar_contents: list[dict] = []
    try:
        from backend.core.memory.semantic_search import search_similar_contents

        query = brief.get("objective") or brief.get("content_type", "")
        if query:
            results = await search_similar_contents(query, client_id, limit=5)
            similar_contents = [r.model_dump() for r in results]
    except Exception as exc:
        logger.warning("content_nodes.similar_contents_search_failed", client_id=client_id, error=str(exc))

    logger.info(
        "content_nodes.context_loaded", client_id=client_id, similar_content_count=len(similar_contents)
    )
    return {
        "editorial_guidelines": guidelines.model_dump(),
        "similar_contents": similar_contents,
        "iterations": 0,
        "max_iterations": DEFAULT_MAX_ITERATIONS,
        "needs_human_review": False,
    }


async def select_template_node(state: ContentState) -> dict:
    """Sélectionne le format/structure approprié selon le brief  un
    ContentTemplate client en base a priorité sur la structure par défaut."""
    client_id = state["client_id"]
    brief = state.get("brief") or {}
    content_type = brief.get("content_type", "article")

    structure = _DEFAULT_STRUCTURES.get(content_type, _DEFAULT_STRUCTURES["article"])
    template_source = "default"
    try:
        from backend.db.repositories.content_repository import ContentTemplateRepository
        from backend.db.session import get_session

        async with get_session() as session:
            templates = await ContentTemplateRepository(session).get_by_client_and_type(
                UUID(client_id), content_type
            )
        if templates:
            structure = templates[0].structure.get("sections", structure)
            template_source = "client"
    except Exception as exc:
        logger.warning("content_nodes.template_load_failed", client_id=client_id, error=str(exc))

    logger.info("content_nodes.template_selected", client_id=client_id, content_type=content_type, source=template_source)
    return {"selected_template": {"template_type": content_type, "structure": structure, "source": template_source}}


def _build_prompt(state: ContentState, evaluation_feedback: str) -> str:
    brief = state.get("brief") or {}
    content_type = brief.get("content_type", "article")
    guidelines = state.get("editorial_guidelines") or {}
    keywords = ", ".join(brief.get("target_keywords") or []) or "aucun"

    if content_type == "post":
        platform = brief.get("platform", "web")
        return get_content_prompt(
            "content-post-social-generation",
            brief=json.dumps(brief, ensure_ascii=False),
            platform=platform,
            platform_constraints=_PLATFORM_CONSTRAINTS.get(platform, _PLATFORM_CONSTRAINTS["web"]),
            guidelines=json.dumps(guidelines, ensure_ascii=False),
            evaluation_feedback=evaluation_feedback,
        )
    if content_type == "email":
        return get_content_prompt(
            "content-email-body-generation",
            brief=json.dumps(brief, ensure_ascii=False),
            target_audience=brief.get("target_audience", "non précisée"),
            guidelines=json.dumps(guidelines, ensure_ascii=False),
            evaluation_feedback=evaluation_feedback,
        )
    if content_type == "landing_page":
        return get_content_prompt(
            "content-landing-page-generation",
            brief=json.dumps(brief, ensure_ascii=False),
            keywords=keywords,
            guidelines=json.dumps(guidelines, ensure_ascii=False),
            evaluation_feedback=evaluation_feedback,
        )
    # "article" et tout type non reconnu (ex. "visual", géré par l'Agent
    # Créatif, pas par l'Agent Content) : le prompt article reste le repli
    # le plus générique.
    return get_content_prompt(
        "content-article-generation",
        brief=json.dumps(brief, ensure_ascii=False),
        keywords=keywords,
        guidelines=json.dumps(guidelines, ensure_ascii=False),
        similar_contents=json.dumps(state.get("similar_contents") or [], ensure_ascii=False),
        evaluation_feedback=evaluation_feedback,
    )


async def generate_draft_node(state: ContentState) -> dict:
    """Génère le contenu avec Qwen3.5 72B, sortie structurée (ContentDraft).
    Feedback loop structuré : le retour de evaluate_quality_node (itération
    précédente) est injecté dans le prompt via `evaluation_feedback`."""
    client_id = state["client_id"]
    evaluation_feedback = (state.get("quality_evaluation") or {}).get(
        "llm_feedback", "aucun (première génération)"
    )
    prompt = _build_prompt(state, evaluation_feedback)

    llm_client = NexusLLMClient()
    try:
        draft = await llm_client.complete_structured(
            prompt=prompt,
            response_model=ContentDraft,
            task_type="content_generation",
            client_id=client_id,
            agent_name="content",
        )
        draft_dict = draft.model_dump()
    except Exception as exc:
        logger.warning("content_nodes.generation_failed", client_id=client_id, error=str(exc))
        draft_dict = state.get("draft") or {"title": "", "body": "", "meta_description": "", "hashtags": []}

    iterations = state.get("iterations", 0) + 1
    logger.info("content_nodes.draft_generated", client_id=client_id, iteration=iterations)
    return {"draft": draft_dict, "iterations": iterations}


async def evaluate_quality_node(state: ContentState) -> dict:
    """Évalue le draft (SEO, ton, pertinence) via le scorer PyTorch
    (ContentScorer) + un jugement LLM ("LLM judge") ; combine les deux en un
    score unique utilisé par la boucle Generator-Evaluator."""
    client_id = state["client_id"]
    draft = state.get("draft") or {}
    body = draft.get("body", "")
    keywords = (state.get("brief") or {}).get("target_keywords") or []

    pytorch_score = (
        _get_content_scorer().score_content(body, keywords)
        if body
        else ContentScore(score_global=0.0, score_seo=0.0, score_readability=0.0, score_engagement=0.0)
    )

    llm_score, feedback, tone_ok, relevance_ok = pytorch_score.score_global, "", True, True
    try:
        prompt = get_content_prompt(
            "content-evaluation",
            draft=json.dumps(draft, ensure_ascii=False),
            guidelines=json.dumps(state.get("editorial_guidelines") or {}, ensure_ascii=False),
            pytorch_score=pytorch_score.score_global,
        )
        llm_client = NexusLLMClient()
        judgment = await llm_client.complete_structured(
            prompt=prompt,
            response_model=QualityJudgment,
            task_type="classification",
            client_id=client_id,
            agent_name="content",
        )
        llm_score, feedback, tone_ok, relevance_ok = (
            judgment.score,
            judgment.feedback,
            judgment.tone_ok,
            judgment.relevance_ok,
        )
    except Exception as exc:
        logger.warning("content_nodes.llm_judge_failed", client_id=client_id, error=str(exc))

    combined_score = (pytorch_score.score_global + llm_score) / 2
    quality_evaluation = {
        "pytorch_score": pytorch_score.model_dump(),
        "llm_score": llm_score,
        "llm_feedback": feedback,
        "tone_ok": tone_ok,
        "relevance_ok": relevance_ok,
        "combined_score": combined_score,
    }
    logger.info("content_nodes.quality_evaluated", client_id=client_id, combined_score=combined_score)
    return {"quality_evaluation": quality_evaluation}


async def evaluate_seo_score_node(state: ContentState) -> dict:
    """Calcule le score SEO du contenu. Réutilise le sous-score SEO déjà
    produit par ContentScorer dans evaluate_quality_node (même embedding,
    mêmes features textuelles) plutôt que de le recalculer  évite un appel
    redondant au modèle d'embedding pour un résultat identique."""
    quality_evaluation = state.get("quality_evaluation") or {}
    seo_score = (quality_evaluation.get("pytorch_score") or {}).get("score_seo", 0.0)
    logger.info("content_nodes.seo_score_evaluated", client_id=state["client_id"], seo_score=seo_score)
    return {"seo_score": seo_score}


def route_after_evaluation(state: ContentState) -> Literal["refine", "retry", "finalize_needs_review"]:
    """Décision de la boucle Generator-Evaluator, basée sur le score combiné
    (PyTorch + LLM judge) produit par evaluate_quality_node.

    Le spec (Prompt 5.3) liste `evaluate_seo_score`/`refine_content` entre
    `evaluate_quality` et `finalize_content` dans l'ordre des nœuds, mais son
    tableau d'arêtes conditionnelles ne nomme que `finalize_content`/
    `generate_draft` comme cibles directes depuis `evaluate_quality`  les
    deux lectures littérales sont incompatibles (sinon `evaluate_seo_score`/
    `refine_content` seraient du code mort, jamais atteint). Résolution
    retenue (cohérente avec le reste de la session : documenter un choix
    explicite plutôt que trancher silencieusement) : score >= seuil ->
    passage par refine_content (léger polish, cf. sa description "affine le
    contenu selon les évaluations") avant finalize_content ; score < seuil et
    itérations restantes -> retour direct à generate_draft (régénération
    complète, pas juste un polish) ; score < seuil et itérations épuisées ->
    finalize_content directement, needs_human_review=True."""
    quality_evaluation = state.get("quality_evaluation") or {}
    combined_score = quality_evaluation.get("combined_score", 0.0)
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", DEFAULT_MAX_ITERATIONS)

    if combined_score >= _QUALITY_THRESHOLD:
        return "refine"
    if iterations < max_iterations:
        return "retry"
    return "finalize_needs_review"


async def refine_content_node(state: ContentState) -> dict:
    """Affine le contenu jugé satisfaisant (score >= seuil) avant
    finalisation : ajustements déterministes (troncature de la
    méta-description à 155 caractères  limite d'affichage SERP standard,
    dédoublonnage des hashtags), sans nouvel appel LLM complet."""
    draft = dict(state.get("draft") or {})
    meta_description = draft.get("meta_description", "")
    if len(meta_description) > 155:
        draft["meta_description"] = meta_description[:152].rstrip() + "..."
    hashtags = draft.get("hashtags") or []
    draft["hashtags"] = list(dict.fromkeys(h for h in hashtags if h))
    logger.info("content_nodes.content_refined", client_id=state["client_id"])
    return {"draft": draft}


async def finalize_content_node(state: ContentState) -> dict:
    """Prépare le contenu final pour publication. `needs_human_review` est
    recalculé ici (plutôt que lu tel quel depuis l'état) : c'est le seul
    point du graphe qui distingue de façon fiable la branche "itérations
    épuisées" de la branche "score satisfaisant", quelle que soit la
    manière dont ce nœud a été atteint."""
    brief = state.get("brief") or {}
    draft = state.get("draft") or {}
    quality_evaluation = state.get("quality_evaluation") or {}
    combined_score = quality_evaluation.get("combined_score", 0.0)
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    needs_human_review = combined_score < _QUALITY_THRESHOLD and iterations >= max_iterations

    content_type = brief.get("content_type", "article")
    platform = brief.get("platform", "web")
    valid_types = {"article", "post", "email", "landing_page", "visual"}
    valid_platforms = {"linkedin", "meta", "tiktok", "email", "web"}

    final = Content(
        id=str(uuid4()),
        type=content_type if content_type in valid_types else "article",
        platform=platform if platform in valid_platforms else "web",
        title=draft.get("title"),
        body=draft.get("body", ""),
        status="review" if needs_human_review else "draft",
        metadata={
            "meta_description": draft.get("meta_description", ""),
            "hashtags": draft.get("hashtags", []),
            "seo_score": state.get("seo_score"),
            "quality_score": combined_score,
            "needs_human_review": needs_human_review,
        },
    )
    logger.info(
        "content_nodes.content_finalized",
        client_id=state["client_id"],
        needs_human_review=needs_human_review,
        combined_score=combined_score,
    )
    return {"final_content": final.model_dump(), "needs_human_review": needs_human_review}


async def store_content_node(state: ContentState) -> dict:
    """Sauvegarde le contenu final dans PostgreSQL (structure relationnelle)
    et Qdrant (recherche sémantique future via search_similar_contents)."""
    client_id = state["client_id"]
    brief = state.get("brief") or {}
    final = state.get("final_content") or {}
    stored_id: str | None = None

    try:
        from backend.db.models.enums import ContentPlatform, ContentStatus, ContentType
        from backend.db.repositories.content_repository import ContentRepository
        from backend.db.session import get_session

        async with get_session() as session:
            obj = await ContentRepository(session).create(
                client_id=UUID(client_id),
                campaign_id=UUID(brief["campaign_id"]) if brief.get("campaign_id") else None,
                agent_source="content",
                content_type=ContentType(final.get("type", "article")),
                title=final.get("title"),
                body=final.get("body", ""),
                platform=ContentPlatform(final.get("platform", "web")),
                status=ContentStatus.REVIEW if state.get("needs_human_review") else ContentStatus.DRAFT,
            )
            stored_id = str(obj.id)
    except Exception as exc:
        logger.warning("content_nodes.postgres_store_failed", client_id=client_id, error=str(exc))

    try:
        from backend.core.memory.collections import COLLECTION_CONTENTS
        from backend.core.memory.embedding_manager import TextEmbedder
        from backend.core.memory.qdrant_client import get_qdrant_client

        point_id = stored_id or final.get("id")
        if point_id and final.get("body"):
            vector = await TextEmbedder().embed_text(final["body"])
            await get_qdrant_client().upsert(
                COLLECTION_CONTENTS.name,
                point_id,
                vector,
                {
                    "content_id": point_id,
                    "client_id": client_id,
                    "content_type": final.get("type"),
                    "platform": final.get("platform"),
                    "title": final.get("title"),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "performance_score": state.get("seo_score"),
                },
            )
    except Exception as exc:
        logger.warning("content_nodes.qdrant_store_failed", client_id=client_id, error=str(exc))

    logger.info("content_nodes.content_stored", client_id=client_id, stored_content_id=stored_id)
    return {"stored_content_id": stored_id}


async def content_reporter_node(state: ContentState) -> dict:
    """Compile et retourne les contenus générés à l'orchestrateur/cluster appelant."""
    final = state.get("final_content")
    generated_contents = [Content.model_validate(final)] if final else []
    logger.info("content_nodes.completed", client_id=state["client_id"], content_count=len(generated_contents))
    return {"generated_contents": generated_contents}
