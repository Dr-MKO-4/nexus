"""Worker pour les tâches marketing temps court  Prompt 6.1."""

import asyncio
from uuid import UUID

import structlog

from backend.tasks.celery_app import celery_app, default_priority_for_queue
from backend.tasks.queues.redis_queue import QUEUE_ANALYTICS, QUEUE_EMAIL, QUEUE_SEO, QUEUE_SOCIAL

logger = structlog.get_logger(__name__)

# Voir llm_worker.py pour la justification complète (inversion business->
# kombu, `Task.apply_async` retombant sur `task_default_priority` sans ce
# `priority=` explicite au niveau du décorateur).
_SOCIAL_PRIORITY = default_priority_for_queue(QUEUE_SOCIAL)
_EMAIL_PRIORITY = default_priority_for_queue(QUEUE_EMAIL)
_ANALYTICS_PRIORITY = default_priority_for_queue(QUEUE_ANALYTICS)
_SEO_PRIORITY = default_priority_for_queue(QUEUE_SEO)


@celery_app.task(bind=True, name="nexus.marketing.publish_social_post_task", queue=QUEUE_SOCIAL, priority=_SOCIAL_PRIORITY, max_retries=2)
def publish_social_post_task(self, content_id: str, platforms: list[str]) -> dict:
    """Publie un Content existant (déjà généré) sur les plateformes
    demandées, via l'Agent Social complet."""
    from backend.agents.social.graph import build_social_graph
    from backend.core.state.state_models import Content
    from backend.db.repositories.content_repository import ContentRepository
    from backend.db.session import get_session

    async def _run() -> dict:
        async with get_session() as session:
            row = await ContentRepository(session).get_by_id(UUID(content_id))
        if row is None:
            raise ValueError(f"publish_social_post_task : content_id introuvable : {content_id!r}")
        if row.platform.value not in platforms:
            logger.info("marketing_worker.publish_skipped_platform_mismatch", content_id=content_id, platform=row.platform.value, platforms=platforms)
            return {"published": False, "reason": "platform_not_requested"}

        content = Content(
            id=str(row.id),
            type=row.content_type.value,
            platform=row.platform.value,
            title=row.title,
            body=row.body,
            status=row.status.value,
            metadata=row.performance_data or {},
        )
        graph = build_social_graph()
        initial_state = {
            "client_id": str(row.client_id),
            "contents": [content],
            "recent_engagement_metrics": [],
            "existing_calendar": [],
            "previously_detected_trends": [],
            "client_name": None,
            "industry": None,
            "adapted_posts": [],
            "publication_schedule": [],
            "publish_results": [],
            "published_contents": [],
            "engagement_metrics": [],
            "detected_trends": [],
            "detected_mentions": [],
            "sentiment_results": [],
            "crisis_alerts": [],
            "social_report": None,
        }
        result = await graph.ainvoke(initial_state)
        return {"published": bool(result.get("published_contents")), "social_report": result.get("social_report")}

    try:
        result = asyncio.run(_run())
        logger.info("marketing_worker.social_post_published", content_id=content_id, platforms=platforms)
        return result
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("marketing_worker.publish_social_post_failed", content_id=content_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="nexus.marketing.send_email_sequence_task", queue=QUEUE_EMAIL, priority=_EMAIL_PRIORITY, max_retries=2)
def send_email_sequence_task(self, contact_ids: list[str], sequence_name: str) -> dict:
    """Déclenche une séquence email pour des contacts et une séquence déjà
    identifiés  appelle directement les nœuds de génération/envoi de
    l'Agent Email (`generate_email_content` -> `optimize_subject_lines` ->
    `schedule_send` -> `trigger_mautic`), SANS repasser par
    `segment_audience`/`select_sequence` : ce sont ces deux nœuds qui
    décident normalement QUI reçoit QUELLE séquence, une décision déjà
    prise ici par les paramètres de la tâche."""
    from backend.agents.email.nodes import generate_email_content_node, optimize_subject_lines_node, schedule_send_node, trigger_mautic_node
    from backend.agents.email.sequence_manager import AVAILABLE_SEQUENCES

    async def _run() -> dict:
        sequence_config = AVAILABLE_SEQUENCES.get(sequence_name)
        if sequence_config is None:
            raise ValueError(f"send_email_sequence_task : sequence_name inconnu : {sequence_name!r}")

        state: dict = {
            "client_id": "",
            "contents": [],
            "contacts": [],
            "sequence_history": [],
            "open_click_rates": {},
            "segments": {},
            "selected_sequences": [
                {"segment": "manual_trigger", "sequence_name": sequence_name, "steps_days": sequence_config.steps_days, "contact_ids": contact_ids}
            ],
            "email_drafts": [],
            "subject_line_variants": [],
            "send_schedule": [],
            "trigger_results": [],
            "email_sequences_triggered": [],
            "tracked_metrics": [],
            "email_report": None,
        }
        state = {**state, **(await generate_email_content_node(state))}
        state = {**state, **(await optimize_subject_lines_node(state))}
        state = {**state, **(await schedule_send_node(state))}
        state = {**state, **(await trigger_mautic_node(state))}
        return {
            "trigger_results": state["trigger_results"],
            "email_sequences_triggered": state["email_sequences_triggered"],
        }

    try:
        result = asyncio.run(_run())
        logger.info("marketing_worker.email_sequence_sent", contact_count=len(contact_ids), sequence_name=sequence_name)
        return result
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("marketing_worker.send_email_sequence_failed", sequence_name=sequence_name, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="nexus.marketing.collect_analytics_task", queue=QUEUE_ANALYTICS, priority=_ANALYTICS_PRIORITY, max_retries=2)
def collect_analytics_task(self, client_id: str, period: str) -> dict:
    """Exécute l'Agent Analytics complet, retourne `analyzed_data`."""
    from backend.agents.analytics.graph import build_analytics_graph

    async def _run() -> dict:
        graph = build_analytics_graph()
        initial_state = {
            "client_id": client_id,
            "raw_metrics": {"period": period},
            "matomo_data": {},
            "campaign_data": {},
            "email_data": {},
            "social_data": {},
            "kpis": {},
            "anomalies": [],
            "attribution": {},
            "insights": [],
            "recommendations": [],
            "metrics_stored": False,
            "analyzed_data": {},
        }
        result = await graph.ainvoke(initial_state)
        return result.get("analyzed_data") or {}

    try:
        result = asyncio.run(_run())
        logger.info("marketing_worker.analytics_collected", client_id=client_id, period=period)
        return result
    except Exception as exc:
        logger.warning("marketing_worker.collect_analytics_failed", client_id=client_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="nexus.marketing.audit_seo_task", queue=QUEUE_SEO, priority=_SEO_PRIORITY, max_retries=2)
def audit_seo_task(self, client_id: str) -> dict:
    """Exécute l'Agent SEO complet (audit technique + mots-clés + briefs)."""
    from backend.agents.seo.graph import build_seo_graph

    async def _run() -> dict:
        graph = build_seo_graph()
        initial_state = {
            "client_id": client_id,
            "brief": None,
            "existing_keywords": [],
            "site_url": None,
            "industry": None,
            "editorial_context": None,
            "keyword_candidates": [],
            "competitor_analysis": None,
            "content_briefs": [],
            "seo_keywords": [],
            "seo_audit_results": None,
        }
        result = await graph.ainvoke(initial_state)
        return {"seo_audit_results": result.get("seo_audit_results"), "seo_keyword_count": len(result.get("seo_keywords") or [])}

    try:
        result = asyncio.run(_run())
        logger.info("marketing_worker.seo_audited", client_id=client_id)
        return result
    except Exception as exc:
        logger.warning("marketing_worker.audit_seo_failed", client_id=client_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, name="nexus.marketing.update_sea_bids_task", queue=QUEUE_SEO, priority=_SEO_PRIORITY, max_retries=2)
def update_sea_bids_task(self, client_id: str) -> dict:
    """Exécute l'Agent SEA complet (analyse de performance + optimisation
    des enchères)  pas de point d'entrée dédié "juste les enchères" dans le
    graphe SEA existant (Prompt 5.2), qui traite l'analyse et l'ajustement
    des enchères comme un pipeline unique (`analyze_performance` ->
    `optimize_bids`) plutôt que des étapes indépendamment déclenchables."""
    from backend.agents.sea.graph import build_sea_graph

    async def _run() -> dict:
        graph = build_sea_graph()
        initial_state = {
            "client_id": client_id,
            "brief": None,
            "active_campaigns": [],
            "campaign_budgets": [],
            "campaign_history": [],
            "customer_id": None,
            "account_id": None,
            "performance_analysis": None,
            "bid_adjustments": [],
            "ad_variants": [],
            "budget_allocation": {},
            "pacing_status": None,
            "overspending_alerts": [],
            "sea_campaigns": [],
        }
        result = await graph.ainvoke(initial_state)
        return {"bid_adjustments": result.get("bid_adjustments") or []}

    try:
        result = asyncio.run(_run())
        logger.info("marketing_worker.sea_bids_updated", client_id=client_id)
        return result
    except Exception as exc:
        logger.warning("marketing_worker.update_sea_bids_failed", client_id=client_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


__all__ = [
    "publish_social_post_task",
    "send_email_sequence_task",
    "collect_analytics_task",
    "audit_seo_task",
    "update_sea_bids_task",
]
