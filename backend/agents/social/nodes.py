"""Implémentation des nœuds de l'Agent Social."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.agents.social.prompts import get_social_prompt
from backend.agents.social.scheduler import avoid_conflicts, get_optimal_slots
from backend.agents.social.state import SocialState
from backend.config.settings import settings
from backend.core.state.state_models import Alert, Content
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.pytorch_models.classifiers.sentiment_classifier import SentimentClassifier
from backend.tools.social.content_adapter import adapt_for_instagram, adapt_for_linkedin, adapt_for_tiktok
from backend.tools.social.n8n_client import (
    WORKFLOW_LINKEDIN_POST,
    WORKFLOW_META_POST,
    WORKFLOW_SOCIAL_METRICS_COLLECT,
    WORKFLOW_TIKTOK_POST,
    N8nClient,
)

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# Adaptateurs structurels (troncature, contraintes dures) par plateforme 
# adapt_for_twitter existe dans tools.social.content_adapter mais n'est câblé
# dans aucun nœud : ContentPlatform (backend.db.models.enums) n'a pas de
# valeur "twitter", donc aucun Content produit par l'Agent Content ne peut
# jamais avoir platform="twitter" ; la fonction reste disponible pour un futur
# usage de cross-posting explicite, pas du code mort par oubli.
_STRUCTURAL_ADAPTERS = {"linkedin": adapt_for_linkedin, "meta": adapt_for_instagram, "tiktok": adapt_for_tiktok}
_PLATFORM_CONSTRAINTS_DESC = {
    "linkedin": "3000 caractères max, ton professionnel, format article si contenu long",
    "meta": "2200 caractères max, jusqu'à 30 hashtags",
    "tiktok": "script vidéo court, accroche dès les premières secondes",
}
_WORKFLOW_BY_PLATFORM = {"linkedin": WORKFLOW_LINKEDIN_POST, "meta": WORKFLOW_META_POST, "tiktok": WORKFLOW_TIKTOK_POST}


class AdaptedPost(BaseModel):
    model_config = _STRICT_CONFIG

    text: str
    hashtags: list[str] = Field(default_factory=list)


class TrendAnalysis(BaseModel):
    model_config = _STRICT_CONFIG

    trends: list[dict] = Field(default_factory=list)
    suggested_angle: str = ""


class CrisisAssessment(BaseModel):
    model_config = _STRICT_CONFIG

    severity: str
    summary: str
    recommended_action: str
    draft_response: str = ""


_sentiment_classifier: SentimentClassifier | None = None


def _get_sentiment_classifier() -> SentimentClassifier:
    global _sentiment_classifier
    if _sentiment_classifier is None:
        _sentiment_classifier = SentimentClassifier.from_checkpoint()
    return _sentiment_classifier


async def _search_searxng(query: str, limit: int = 10) -> list[dict]:
    """Recherche générique via SearXNG (même service self-hosted que
    tools.seo.keyword_research.search_keywords_searxng, mais pas la même
    forme de résultat  ici des mentions/tendances brutes, pas des
    KeywordData) : pas d'appel API tierce payante pour ce besoin de veille."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{settings.SEARXNG_BASE_URL}/search", params={"q": query, "format": "json"})
        response.raise_for_status()
        body = response.json()
    results = body.get("results", [])[:limit]
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")} for r in results]


async def load_social_context_node(state: SocialState) -> dict:
    """Charge les métriques d'engagement récentes, le calendrier existant
    (contenus déjà publiés) et le profil client (nom, secteur)."""
    client_id = state["client_id"]
    recent_engagement_metrics: list[dict] = []
    existing_calendar: list[dict] = []
    client_name: str | None = None
    industry: str | None = None
    previously_detected_trends: list[dict] = []

    try:
        from backend.db.models.enums import ContentStatus
        from backend.db.repositories.client_repository import ClientRepository
        from backend.db.repositories.content_repository import ContentRepository
        from backend.db.repositories.performance_repository import AgentDecisionRepository, PerformanceMetricRepository
        from backend.db.session import get_session

        async with get_session() as session:
            client = await ClientRepository(session).get_by_id(UUID(client_id))
            published = await ContentRepository(session).get_published(UUID(client_id))
            metrics = await PerformanceMetricRepository(session).get_by_channel_and_period(
                UUID(client_id),
                "social",
                datetime.now(timezone.utc) - timedelta(days=30),
                datetime.now(timezone.utc),
            )
            trend_decisions = await AgentDecisionRepository(session).get_by_agent(UUID(client_id), "social")
        if client is not None:
            client_name = client.name
            industry = client.industry
        existing_calendar = [
            {"content_id": str(c.id), "platform": c.platform.value, "published_at": c.published_at.isoformat() if c.published_at else None}
            for c in published
        ]
        recent_engagement_metrics = [
            {"metric_name": m.metric_name, "metric_value": m.metric_value, "period_start": m.period_start.isoformat()}
            for m in metrics
        ]
        # AgentDecisionRepository.get_by_agent trie déjà par created_at desc
        # (voir performance_repository.py) : la première décision de type
        # "trend_detection" trouvée est la plus récente.
        last_trend_decision = next((d for d in trend_decisions if d.decision_type == "trend_detection"), None)
        if last_trend_decision is not None:
            previously_detected_trends = last_trend_decision.decision_data.get("trends", [])
    except Exception as exc:
        logger.warning("social_nodes.load_context_failed", client_id=client_id, error=str(exc))

    logger.info(
        "social_nodes.context_loaded",
        client_id=client_id,
        existing_calendar_count=len(existing_calendar),
        metric_count=len(recent_engagement_metrics),
        previously_detected_trend_count=len(previously_detected_trends),
    )
    return {
        "recent_engagement_metrics": recent_engagement_metrics,
        "existing_calendar": existing_calendar,
        "previously_detected_trends": previously_detected_trends,
        "client_name": client_name,
        "industry": industry,
    }


async def adapt_content_per_platform_node(state: SocialState) -> dict:
    """Adapte chaque contenu à sa plateforme : réécriture de ton via LLM
    (CONTENT_ADAPTATION_PROMPT), puis application des contraintes dures
    (longueur, hashtags) via tools.content_adapter."""
    client_id = state["client_id"]
    contents = state.get("contents") or []
    llm_client = NexusLLMClient()
    adapted_posts: list[dict] = []

    for content in contents:
        platform = content.platform
        adapter = _STRUCTURAL_ADAPTERS.get(platform)
        if adapter is None:
            logger.debug("social_nodes.platform_not_supported", content_id=content.id, platform=platform)
            continue

        working_content = content
        try:
            prompt = get_social_prompt(
                "social-content-adaptation",
                content=json.dumps({"title": content.title, "body": content.body}, ensure_ascii=False),
                platform=platform,
                platform_constraints=_PLATFORM_CONSTRAINTS_DESC[platform],
            )
            adapted = await llm_client.complete_structured(
                prompt=prompt,
                response_model=AdaptedPost,
                task_type="content_generation",
                client_id=client_id,
                agent_name="social",
            )
            working_content = content.model_copy(
                update={"body": adapted.text, "metadata": {**content.metadata, "hashtags": adapted.hashtags}}
            )
        except Exception as exc:
            logger.warning("social_nodes.adaptation_llm_failed", content_id=content.id, platform=platform, error=str(exc))

        structural = adapter(working_content)
        adapted_posts.append({"content_id": content.id, "platform": platform, "adapted": structural.model_dump()})

    logger.info("social_nodes.content_adapted", client_id=client_id, adapted_count=len(adapted_posts))
    return {"adapted_posts": adapted_posts}


async def schedule_publications_node(state: SocialState) -> dict:
    """Détermine les créneaux optimaux par plateforme (scheduler.py), en
    évitant les conflits avec le calendrier existant."""
    client_id = state["client_id"]
    adapted_posts = state.get("adapted_posts") or []
    existing_times = [
        datetime.fromisoformat(e["published_at"]) for e in (state.get("existing_calendar") or []) if e.get("published_at")
    ]

    by_platform: dict[str, list[dict]] = {}
    for post in adapted_posts:
        by_platform.setdefault(post["platform"], []).append(post)

    schedule: list[dict] = []
    for platform, posts in by_platform.items():
        try:
            slots = await get_optimal_slots(platform, client_id, len(posts))
            slots = avoid_conflicts(slots, existing_times)
        except Exception as exc:
            logger.warning("social_nodes.scheduling_failed", client_id=client_id, platform=platform, error=str(exc))
            slots = [datetime.now(timezone.utc) + timedelta(hours=i + 1) for i in range(len(posts))]
        for post, slot in zip(posts, slots):
            schedule.append({"content_id": post["content_id"], "platform": platform, "scheduled_at": slot.isoformat()})

    logger.info("social_nodes.publications_scheduled", client_id=client_id, scheduled_count=len(schedule))
    return {"publication_schedule": schedule}


async def publish_content_node(state: SocialState) -> dict:
    """Publie via n8n API (un workflow par plateforme), puis met à jour le
    statut du Content en base (best-effort)."""
    client_id = state["client_id"]
    schedule = state.get("publication_schedule") or []
    adapted_by_id = {p["content_id"]: p["adapted"] for p in (state.get("adapted_posts") or [])}

    publish_results: list[dict] = []
    published_contents: list[str] = []
    n8n = N8nClient()
    try:
        for item in schedule:
            content_id, platform = item["content_id"], item["platform"]
            workflow_id = _WORKFLOW_BY_PLATFORM.get(platform)
            if workflow_id is None:
                continue
            try:
                execution = await n8n.trigger_workflow(
                    workflow_id,
                    {"content_id": content_id, "scheduled_at": item["scheduled_at"], **adapted_by_id.get(content_id, {})},
                )
                publish_results.append(
                    {"content_id": content_id, "platform": platform, "execution_id": execution.execution_id, "status": execution.status}
                )
                published_contents.append(content_id)
            except Exception as exc:
                logger.warning("social_nodes.publish_failed", content_id=content_id, platform=platform, error=str(exc))
                publish_results.append({"content_id": content_id, "platform": platform, "status": "failed", "error": str(exc)})
    finally:
        await n8n.aclose()

    try:
        from backend.db.models.enums import ContentStatus
        from backend.db.repositories.content_repository import ContentRepository
        from backend.db.session import get_session

        async with get_session() as session:
            repo = ContentRepository(session)
            for content_id in published_contents:
                await repo.update(UUID(content_id), status=ContentStatus.PUBLISHED, published_at=datetime.now(timezone.utc))
    except Exception as exc:
        logger.warning("social_nodes.status_update_failed", client_id=client_id, error=str(exc))

    logger.info("social_nodes.content_published", client_id=client_id, published_count=len(published_contents))
    return {"publish_results": publish_results, "published_contents": published_contents}


_METRICS_POLL_ATTEMPTS = 3
_METRICS_POLL_DELAY_SECONDS = 1.0


async def monitor_engagement_node(state: SocialState) -> dict:
    """Collecte les métriques post-publication via le workflow n8n
    SOCIAL_METRICS_COLLECT : déclenche la collecte, puis interroge
    get_workflow_status un court instant (le workflow n8n s'exécute de façon
    asynchrone côté serveur) pour tenter de récupérer le résultat directement
    plutôt que de se contenter d'enregistrer que la collecte a été demandée."""
    client_id = state["client_id"]
    published_contents = state.get("published_contents") or []
    engagement_metrics: list[dict] = []

    if published_contents:
        n8n = N8nClient()
        try:
            execution = await n8n.trigger_workflow(WORKFLOW_SOCIAL_METRICS_COLLECT, {"content_ids": published_contents})
            metric_entry = {"execution_id": execution.execution_id, "status": execution.status, "data": None}

            for _ in range(_METRICS_POLL_ATTEMPTS):
                if not execution.execution_id:
                    break
                try:
                    status = await n8n.get_workflow_status(execution.execution_id)
                except Exception as exc:
                    logger.debug("social_nodes.metrics_poll_failed", client_id=client_id, error=str(exc))
                    break
                if status.finished:
                    metric_entry = {"execution_id": execution.execution_id, "status": status.status, "data": status.data}
                    break
                await asyncio.sleep(_METRICS_POLL_DELAY_SECONDS)

            engagement_metrics.append(metric_entry)
        except Exception as exc:
            logger.warning("social_nodes.metrics_collection_failed", client_id=client_id, error=str(exc))
        finally:
            await n8n.aclose()

    logger.info("social_nodes.engagement_monitored", client_id=client_id, metric_count=len(engagement_metrics))
    return {"engagement_metrics": engagement_metrics}


async def detect_trends_node(state: SocialState) -> dict:
    """Détecte les tendances (secteur) et mentions (marque) via SearXNG,
    puis synthèse LLM des tendances (TREND_ANALYSIS_PROMPT). Persiste le
    résultat via AgentDecisionRepository pour que load_social_context_node
    puisse le recharger à l'exécution suivante (spec : "charge... les
    tendances détectées")."""
    client_id = state["client_id"]
    industry = state.get("industry") or "marketing digital"
    client_name = state.get("client_name")
    known_trends = state.get("previously_detected_trends") or []

    detected_trends: list[dict] = []
    detected_mentions: list[dict] = []

    try:
        trend_results = await _search_searxng(f"tendances {industry} réseaux sociaux")
        llm_client = NexusLLMClient()
        prompt = get_social_prompt(
            "social-trend-analysis",
            industry=industry,
            search_results=json.dumps(trend_results, ensure_ascii=False),
            known_trends=json.dumps(known_trends, ensure_ascii=False) if known_trends else "aucune",
        )
        analysis = await llm_client.complete_structured(
            prompt=prompt, response_model=TrendAnalysis, task_type="content_generation", client_id=client_id, agent_name="social"
        )
        detected_trends = analysis.trends
    except Exception as exc:
        logger.warning("social_nodes.trend_detection_failed", client_id=client_id, error=str(exc))

    if client_name:
        try:
            detected_mentions = await _search_searxng(f'"{client_name}" avis OR mention OR commentaire')
        except Exception as exc:
            logger.warning("social_nodes.mention_detection_failed", client_id=client_id, error=str(exc))

    if detected_trends:
        try:
            from backend.db.repositories.performance_repository import AgentDecisionRepository
            from backend.db.session import get_session

            async with get_session() as session:
                await AgentDecisionRepository(session).create(
                    client_id=UUID(client_id),
                    agent_name="social",
                    decision_type="trend_detection",
                    decision_data={"trends": detected_trends, "detected_at": datetime.now(timezone.utc).isoformat()},
                )
        except Exception as exc:
            logger.warning("social_nodes.trend_persist_failed", client_id=client_id, error=str(exc))

    logger.info(
        "social_nodes.trends_detected", client_id=client_id, trend_count=len(detected_trends), mention_count=len(detected_mentions)
    )
    return {"detected_trends": detected_trends, "detected_mentions": detected_mentions}


async def sentiment_analysis_node(state: SocialState) -> dict:
    """Analyse le sentiment des mentions détectées (SentimentClassifier)."""
    client_id = state["client_id"]
    mentions = state.get("detected_mentions") or []
    texts = [f"{m.get('title', '')} {m.get('snippet', '')}".strip() for m in mentions]

    classifier = _get_sentiment_classifier()
    results = classifier.analyze_batch(texts) if texts else []

    logger.info("social_nodes.sentiment_analyzed", client_id=client_id, mention_count=len(texts))
    return {"sentiment_results": [r.model_dump() for r in results]}


async def crisis_detector_node(state: SocialState) -> dict:
    """Détecte une crise de réputation naissante à partir du sentiment agrégé
    des mentions, et propose une réponse (CRISIS_RESPONSE_PROMPT) si le
    signal est confirmé."""
    client_id = state["client_id"]
    mentions = state.get("detected_mentions") or []
    texts = [f"{m.get('title', '')} {m.get('snippet', '')}".strip() for m in mentions]

    classifier = _get_sentiment_classifier()
    is_crisis = classifier.detect_crisis_signal(texts, threshold=0.7) if texts else False

    crisis_alerts: list[Alert] = []
    if is_crisis:
        sentiment_results = state.get("sentiment_results") or []
        negative_signals = [
            m for m, r in zip(mentions, sentiment_results) if r.get("is_crisis_signal")
        ]
        severity, summary = "medium", "Signal de crise détecté (analyse LLM indisponible)."
        try:
            llm_client = NexusLLMClient()
            prompt = get_social_prompt(
                "social-crisis-response",
                negative_signals=json.dumps(negative_signals, ensure_ascii=False),
                brand_context=state.get("client_name") or "non précisé",
            )
            assessment = await llm_client.complete_structured(
                prompt=prompt, response_model=CrisisAssessment, task_type="classification", client_id=client_id, agent_name="social"
            )
            severity, summary = assessment.severity, assessment.summary
        except Exception as exc:
            logger.warning("social_nodes.crisis_assessment_llm_failed", client_id=client_id, error=str(exc))

        crisis_alerts.append(
            Alert(
                level="critical" if severity == "high" else "warning",
                source="crisis_detector",
                message=summary,
                action_required=True,
            )
        )
        logger.warning("social_nodes.crisis_detected", client_id=client_id, severity=severity)

    return {"crisis_alerts": crisis_alerts}


async def social_reporter_node(state: SocialState) -> dict:
    """Compile et retourne les résultats à l'orchestrateur/cluster appelant."""
    sentiment_results = state.get("sentiment_results") or []
    sentiment_summary = {
        label: sum(1 for r in sentiment_results if r.get("label") == label) for label in ("positif", "neutre", "négatif")
    }
    report = {
        "published_count": len(state.get("published_contents") or []),
        "engagement_metrics": state.get("engagement_metrics") or [],
        "detected_trends": state.get("detected_trends") or [],
        "mention_count": len(state.get("detected_mentions") or []),
        "sentiment_summary": sentiment_summary,
        "crisis_alert_count": len(state.get("crisis_alerts") or []),
    }
    logger.info("social_nodes.report_compiled", client_id=state["client_id"], published_count=report["published_count"])
    return {"social_report": report}
