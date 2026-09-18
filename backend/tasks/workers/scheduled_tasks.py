"""Tâches périodiques via Celery Beat  Prompt 6.1.

Peuple `celery_app.conf.beat_schedule` à l'import de ce module (voir
`celery_app.py: imports`, qui ne liste PAS ce fichier  il doit être importé
explicitement par le process Celery Beat, ex.
`celery -A backend.tasks.celery_app beat -S ...` avec ce module chargé, ou
`from backend.tasks.workers import scheduled_tasks` avant le démarrage de
Beat  sinon `beat_schedule` reste vide)."""

import asyncio

import structlog
from celery.schedules import crontab

from backend.tasks.celery_app import celery_app
from backend.tasks.queues.redis_queue import QUEUE_ANALYTICS, QUEUE_LLM, QUEUE_SEO

logger = structlog.get_logger(__name__)


async def _list_client_ids() -> list[str]:
    from backend.db.repositories.client_repository import ClientRepository
    from backend.db.session import get_session

    try:
        async with get_session() as session:
            clients = await ClientRepository(session).list(limit=1000)
        return [str(c.id) for c in clients]
    except Exception as exc:
        logger.warning("scheduled_tasks.list_clients_failed", error=str(exc))
        return []


@celery_app.task(name="nexus.scheduled.daily_analytics_collection", queue=QUEUE_ANALYTICS)
def daily_analytics_collection() -> dict:
    """Tous les jours à 6h00 : collecte Analytics pour chaque client."""
    from backend.tasks.workers.marketing_worker import collect_analytics_task

    client_ids = asyncio.run(_list_client_ids())
    for client_id in client_ids:
        collect_analytics_task.delay(client_id, "daily")
    logger.info("scheduled_tasks.daily_analytics_dispatched", client_count=len(client_ids))
    return {"dispatched": len(client_ids)}


@celery_app.task(name="nexus.scheduled.weekly_seo_audit", queue=QUEUE_SEO)
def weekly_seo_audit() -> dict:
    """Tous les lundis à 7h00 : audit SEO pour chaque client."""
    from backend.tasks.workers.marketing_worker import audit_seo_task

    client_ids = asyncio.run(_list_client_ids())
    for client_id in client_ids:
        audit_seo_task.delay(client_id)
    logger.info("scheduled_tasks.weekly_seo_audit_dispatched", client_count=len(client_ids))
    return {"dispatched": len(client_ids)}


@celery_app.task(name="nexus.scheduled.weekly_report_generation", queue=QUEUE_LLM)
def weekly_report_generation() -> dict:
    """Tous les lundis à 8h00 : génération du rapport hebdomadaire pour
    chaque client  réutilise `llm_worker.run_agent_task` (pas de tâche
    dédiée "reporting" dans marketing_worker.py, le spec ne l'y liste pas :
    l'Agent Reporting est invoqué via le dispatcher générique par agent_name,
    comme n'importe quel autre agent)."""
    from uuid import uuid4

    from backend.tasks.workers.llm_worker import run_agent_task

    client_ids = asyncio.run(_list_client_ids())
    for client_id in client_ids:
        initial_state = {
            "client_id": client_id,
            "analyzed_data": None,
            "anomalies": [],
            "period": None,
            "recipient_emails": [],
            "kpis": {},
            "decisions": [],
            "executive_summary": "",
            "channel_performance": {},
            "recommendations": [],
            "next_week_plan": "",
            "weekly_report": None,
            "approved": False,
            "hitl_feedback": None,
            "report_id": None,
            "report_url": None,
            "delivered": False,
            "report_data": {},
        }
        run_agent_task.delay("reporting", initial_state, f"weekly-report-{client_id}-{uuid4().hex[:8]}")
    logger.info("scheduled_tasks.weekly_report_generation_dispatched", client_count=len(client_ids))
    return {"dispatched": len(client_ids)}


@celery_app.task(name="nexus.scheduled.hourly_sea_performance_check", queue=QUEUE_SEO)
def hourly_sea_performance_check() -> dict:
    """Toutes les heures (heures ouvrées, voir `beat_schedule` ci-dessous) :
    vérification des performances SEA pour chaque client."""
    from backend.tasks.workers.marketing_worker import update_sea_bids_task

    client_ids = asyncio.run(_list_client_ids())
    for client_id in client_ids:
        update_sea_bids_task.delay(client_id)
    logger.info("scheduled_tasks.hourly_sea_check_dispatched", client_count=len(client_ids))
    return {"dispatched": len(client_ids)}


@celery_app.task(name="nexus.scheduled.daily_email_sequence_processor", queue=QUEUE_LLM)
def daily_email_sequence_processor() -> dict:
    """Tous les jours à 9h00 : exécute l'Agent Email complet pour chaque
    client (segmentation + sélection de séquence + envoi  contrairement à
    `send_email_sequence_task`, qui suppose déjà connus les contacts/la
    séquence)."""
    from uuid import uuid4

    from backend.tasks.workers.llm_worker import run_agent_task

    client_ids = asyncio.run(_list_client_ids())
    for client_id in client_ids:
        initial_state = {
            "client_id": client_id,
            "contents": [],
            "contacts": [],
            "sequence_history": [],
            "open_click_rates": {},
            "segments": {},
            "selected_sequences": [],
            "email_drafts": [],
            "subject_line_variants": [],
            "send_schedule": [],
            "trigger_results": [],
            "email_sequences_triggered": [],
            "tracked_metrics": [],
            "email_report": None,
        }
        run_agent_task.delay("email", initial_state, f"daily-email-{client_id}-{uuid4().hex[:8]}")
    logger.info("scheduled_tasks.daily_email_processor_dispatched", client_count=len(client_ids))
    return {"dispatched": len(client_ids)}


@celery_app.task(name="nexus.scheduled.daily_budget_reset")
def daily_budget_reset() -> dict:
    """Tous les jours à minuit : nettoyage des compteurs de coût LLM Redis.

    Les clés `llm_cost:{date}:...` (voir `llm/gateway/cost_tracker.py`) sont
    déjà namespacées par date ET déjà TTL 24h  un nouveau jour démarre donc
    naturellement à zéro sans action explicite. Cette tâche supprime malgré
    tout proactivement les clés des jours PASSÉS (pas celles d'aujourd'hui)
    plutôt que d'attendre leur expiration TTL  utile si le TTL a été
    contourné (ex. `SET`/`INCRBYFLOAT` sans `EXPIRE` suite à un bug futur) ou
    simplement pour garder Redis propre sans dépendre uniquement du TTL."""
    from datetime import datetime, timezone

    async def _reset() -> int:
        from backend.core.memory.redis_client import get_redis_client

        redis_client = get_redis_client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        keys = await redis_client.scan_keys("llm_cost:*")
        stale_keys = [k for k in keys if not k.startswith(f"llm_cost:{today}:")]
        for key in stale_keys:
            await redis_client.delete(key)
        return len(stale_keys)

    try:
        deleted = asyncio.run(_reset())
    except Exception as exc:
        logger.warning("scheduled_tasks.budget_reset_failed", error=str(exc))
        return {"deleted": 0, "error": str(exc)}

    logger.info("scheduled_tasks.budget_reset_completed", deleted_count=deleted)
    return {"deleted": deleted}


@celery_app.task(name="nexus.scheduled.weekly_memory_cleanup")
def weekly_memory_cleanup() -> dict:
    """Tous les dimanches à 2h00 : supprime les embeddings Qdrant orphelins.

    Limite assumée : un "orphelin" n'est bien défini que pour les
    collections adossées 1:1 à une table PostgreSQL identifiable par id
    (`contents` -> Content, `campaigns` -> Campaign, `keywords` -> Keyword).
    `brand_knowledge`/`audiences`/`visual_references` n'ont pas de ligne
    PostgreSQL propriétaire unique (connaissance de marque libre, segments
    dérivés, références stylistiques réutilisables)  non nettoyées ici, pas
    un oubli."""
    from uuid import UUID

    async def _cleanup_collection(collection_name: str, id_payload_key: str, exists_check) -> int:
        from backend.core.memory.qdrant_client import get_qdrant_client

        qdrant = get_qdrant_client()
        client = qdrant._client  # accès direct au client Qdrant pour scroll (pas exposé par le wrapper)
        deleted = 0
        offset = None
        while True:
            points, offset = await client.scroll(collection_name=collection_name, limit=100, offset=offset, with_payload=True)
            if not points:
                break
            for point in points:
                entity_id = (point.payload or {}).get(id_payload_key)
                if entity_id and not await exists_check(entity_id):
                    await qdrant.delete(collection_name, str(point.id))
                    deleted += 1
            if offset is None:
                break
        return deleted

    async def _content_exists(content_id: str) -> bool:
        from backend.db.repositories.content_repository import ContentRepository
        from backend.db.session import get_session

        async with get_session() as session:
            return await ContentRepository(session).exists(UUID(content_id))

    async def _campaign_exists(campaign_id: str) -> bool:
        from backend.db.repositories.campaign_repository import CampaignRepository
        from backend.db.session import get_session

        async with get_session() as session:
            return await CampaignRepository(session).exists(UUID(campaign_id))

    async def _run() -> dict:
        from backend.core.memory.collections import COLLECTION_CAMPAIGNS, COLLECTION_CONTENTS

        # COLLECTION_KEYWORDS exclue : son payload_schema (client_id/keyword/
        # cluster_name/search_volume/difficulty, voir collections.py) ne
        # porte aucun id PostgreSQL individuel par point  pas de vérification
        # d'orphelin possible sans risquer de supprimer à tort.
        return {
            COLLECTION_CONTENTS.name: await _cleanup_collection(COLLECTION_CONTENTS.name, "content_id", _content_exists),
            COLLECTION_CAMPAIGNS.name: await _cleanup_collection(COLLECTION_CAMPAIGNS.name, "campaign_id", _campaign_exists),
        }

    try:
        results = asyncio.run(_run())
    except Exception as exc:
        logger.warning("scheduled_tasks.memory_cleanup_failed", error=str(exc))
        return {"error": str(exc)}

    logger.info("scheduled_tasks.memory_cleanup_completed", **results)
    return results


# ── Programmation Celery Beat ────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "daily-analytics-collection": {
        "task": "nexus.scheduled.daily_analytics_collection",
        "schedule": crontab(hour=6, minute=0),
    },
    "weekly-seo-audit": {
        "task": "nexus.scheduled.weekly_seo_audit",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
    },
    "weekly-report-generation": {
        "task": "nexus.scheduled.weekly_report_generation",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
    "hourly-sea-performance-check": {
        "task": "nexus.scheduled.hourly_sea_performance_check",
        # "Heures ouvrées" : 8h-18h, du lundi au vendredi  choix documenté,
        # non précisé par le spec au-delà de "heures ouvrées".
        "schedule": crontab(minute=0, hour="8-18", day_of_week="1-5"),
    },
    "daily-email-sequence-processor": {
        "task": "nexus.scheduled.daily_email_sequence_processor",
        "schedule": crontab(hour=9, minute=0),
    },
    "daily-budget-reset": {
        "task": "nexus.scheduled.daily_budget_reset",
        "schedule": crontab(hour=0, minute=0),
    },
    "weekly-memory-cleanup": {
        "task": "nexus.scheduled.weekly_memory_cleanup",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
    },
}


__all__ = [
    "daily_analytics_collection",
    "weekly_seo_audit",
    "weekly_report_generation",
    "hourly_sea_performance_check",
    "daily_email_sequence_processor",
    "daily_budget_reset",
    "weekly_memory_cleanup",
]
