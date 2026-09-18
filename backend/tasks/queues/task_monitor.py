"""Monitoring des queues Celery en temps réel  Prompt 6.1."""

import asyncio

import structlog
from pydantic import BaseModel, ConfigDict

from backend.tasks.celery_app import QUEUE_PRIORITIES
from backend.tasks.queues.redis_queue import get_queue_length

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class WorkerStats(BaseModel):
    model_config = _STRICT_CONFIG

    hostname: str
    active_task_count: int
    processed_total: int
    concurrency: int


class FailedTask(BaseModel):
    model_config = _STRICT_CONFIG

    task_id: str
    task_name: str
    error: str
    timestamp: str | None = None


async def get_queue_depths() -> dict[str, int]:
    """Profondeur de chaque queue nommée du spec (toutes les priorités
    confondues  voir `redis_queue.get_queue_length`)."""
    depths: dict[str, int] = {}
    for queue_name in QUEUE_PRIORITIES:
        try:
            depths[queue_name] = await get_queue_length(queue_name)
        except Exception as exc:
            logger.warning("task_monitor.queue_depth_failed", queue=queue_name, error=str(exc))
            depths[queue_name] = -1
    return depths


async def get_worker_stats() -> dict[str, WorkerStats]:
    """Statistiques par worker connecté (`celery_app.control.inspect()` 
    API synchrone de Celery, déportée via `asyncio.to_thread`, même
    contrainte que `redis_queue.py`)."""
    from backend.tasks.celery_app import celery_app

    def _inspect() -> dict:
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        stats = inspector.stats() or {}
        return {"active": active, "stats": stats}

    try:
        raw = await asyncio.to_thread(_inspect)
    except Exception as exc:
        logger.warning("task_monitor.worker_stats_failed", error=str(exc))
        return {}

    worker_stats: dict[str, WorkerStats] = {}
    for hostname, stats in raw["stats"].items():
        active_tasks = raw["active"].get(hostname, [])
        pool_info = stats.get("pool", {})
        worker_stats[hostname] = WorkerStats(
            hostname=hostname,
            active_task_count=len(active_tasks),
            processed_total=int(stats.get("total", {}).get("total", 0)) if isinstance(stats.get("total"), dict) else 0,
            concurrency=int(pool_info.get("max-concurrency", 0) or 0),
        )
    return worker_stats


async def get_failed_tasks(queue: str, limit: int = 100) -> list[FailedTask]:
    """Tâches échouées récentes sur `queue`  lues depuis le backend de
    résultats Celery (Redis). Limite honnête : le backend Redis de Celery
    n'indexe pas nativement "les résultats par queue d'origine" (seulement
    par task_id)  cette fonction scanne les clés de résultat FAILURE
    disponibles et ne filtre PAS réellement par `queue` (l'information de
    queue d'origine n'est pas dans le résultat stocké), contrairement à ce
    que son paramètre suggère. Limite assumée du backend Redis simple, pas
    une omission silencieuse  un vrai filtrage par queue nécessiterait un
    index applicatif dédié (ex. une clé Redis annexe queue->task_ids
    peuplée à l'enqueue), non demandé par ce prompt."""
    from backend.core.memory.redis_client import get_redis_client

    redis_client = get_redis_client()
    try:
        result_keys = await redis_client.scan_keys("celery-task-meta-*")
    except Exception as exc:
        logger.warning("task_monitor.get_failed_tasks_scan_failed", queue=queue, error=str(exc))
        return []

    failed_tasks: list[FailedTask] = []
    for key in result_keys:
        if len(failed_tasks) >= limit:
            break
        try:
            meta = await redis_client.get(key)
        except Exception:
            continue
        if not isinstance(meta, dict) or meta.get("status") != "FAILURE":
            continue
        failed_tasks.append(
            FailedTask(
                task_id=meta.get("task_id", key.replace("celery-task-meta-", "")),
                task_name=meta.get("task_name") or meta.get("name", "unknown"),
                error=str(meta.get("result", meta.get("traceback", "")))[:500],
                timestamp=meta.get("date_done"),
            )
        )

    logger.info("task_monitor.failed_tasks_fetched", queue=queue, count=len(failed_tasks))
    return failed_tasks


async def retry_failed_task(task_id: str) -> bool:
    """Republie une tâche échouée  nécessite de retrouver son nom et ses
    arguments d'origine (stockés dans le résultat Celery si
    `result_extended=True`, sinon indisponibles). Retourne `False`
    proprement si l'information est insuffisante pour rejouer la tâche,
    plutôt que de lever."""
    from backend.core.memory.redis_client import get_redis_client
    from backend.tasks.queues.redis_queue import enqueue_task

    redis_client = get_redis_client()
    meta = await redis_client.get(f"celery-task-meta-{task_id}")
    if not isinstance(meta, dict):
        logger.warning("task_monitor.retry_failed_task_no_metadata", task_id=task_id)
        return False

    task_name = meta.get("task_name") or meta.get("name")
    queue_name = meta.get("queue")
    args = meta.get("args") or []
    kwargs = meta.get("kwargs") or {}
    if not task_name or not queue_name:
        logger.warning("task_monitor.retry_failed_task_insufficient_metadata", task_id=task_id)
        return False

    await enqueue_task(queue_name, task_name, {**kwargs, "_original_args": args})
    logger.info("task_monitor.task_retried", original_task_id=task_id, task_name=task_name)
    return True


# ── Collecteur Prometheus custom ────────────────────────────────────────────


class QueueMetricsCollector:
    """Collecteur `prometheus_client` custom : queue depths, worker counts,
    task rates  enregistré auprès du registre Prometheus par
    `core/monitoring/metrics_exporter.py` (Prompt 6.2, pas encore construit
    dans ce projet) ; exposé ici pour que ce module reste utilisable dès
    maintenant sans dépendre de ce prompt futur."""

    def collect(self):
        from prometheus_client.core import GaugeMetricFamily

        queue_depths = asyncio.run(get_queue_depths())
        depth_metric = GaugeMetricFamily("nexus_queue_depth", "Nombre de tâches en attente par queue", labels=["queue"])
        for queue_name, depth in queue_depths.items():
            depth_metric.add_metric([queue_name], max(depth, 0))
        yield depth_metric

        worker_stats = asyncio.run(get_worker_stats())
        worker_metric = GaugeMetricFamily("nexus_worker_active_tasks", "Tâches actives par worker", labels=["worker"])
        for hostname, stats in worker_stats.items():
            worker_metric.add_metric([hostname], stats.active_task_count)
        yield worker_metric

        count_metric = GaugeMetricFamily("nexus_workers_total", "Nombre de workers connectés", labels=[])
        count_metric.add_metric([], len(worker_stats))
        yield count_metric


__all__ = [
    "WorkerStats",
    "FailedTask",
    "get_queue_depths",
    "get_worker_stats",
    "get_failed_tasks",
    "retry_failed_task",
    "QueueMetricsCollector",
]
