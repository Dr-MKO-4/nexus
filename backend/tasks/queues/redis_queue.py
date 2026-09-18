"""Interface de publication dans les queues Celery, backées par Redis.

Note d'implémentation : l'API cliente de Celery (`send_task`, `AsyncResult`,
`control.revoke`) est synchrone par nature (elle parle à Redis via kombu, pas
via `redis.asyncio`). Pour respecter la contrainte "tout async" de cette
couche tout en restant réellement interopérable avec les workers Celery
définis dans docker-compose.yml (plutôt que de réimplémenter le protocole de
message de Celery à la main par-dessus `redis.asyncio`, fragile et
divergent), ces opérations sont exposées comme des coroutines en déportant
les appels bloquants via `asyncio.to_thread`. Seule `get_queue_length`
interroge directement Redis en async : avec le transport Redis de Celery,
chaque queue est une liste Redis native, dont la longueur se lit sans passer
par l'API Celery.

L'import de `backend.tasks.celery_app` est différé (à l'intérieur de chaque
fonction) : ce module n'existe pas encore à ce stade de la mise en place
(prévu en Phase 4)  le différer permet à `redis_queue.py` et à
`get_queue_length` de rester utilisables/importables indépendamment.
"""

import asyncio
from enum import Enum
from typing import Any

import structlog

from backend.core.memory.redis_client import get_redis_client

logger = structlog.get_logger(__name__)

# Noms des queues Celery (alignés sur stack_technique.md et docker-compose.yml)
QUEUE_ORCHESTRATION = "orchestration"
QUEUE_LLM = "llm_inference"
QUEUE_IMAGE = "image_generation"
QUEUE_EMAIL = "email_dispatch"
QUEUE_SOCIAL = "social_publish"
QUEUE_ANALYTICS = "analytics"
QUEUE_SEO = "seo_tasks"


class TaskStatus(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    RETRY = "retry"
    SUCCESS = "success"
    FAILURE = "failure"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


_CELERY_STATUS_MAP: dict[str, TaskStatus] = {
    "PENDING": TaskStatus.PENDING,
    "STARTED": TaskStatus.STARTED,
    "RETRY": TaskStatus.RETRY,
    "SUCCESS": TaskStatus.SUCCESS,
    "FAILURE": TaskStatus.FAILURE,
    "REVOKED": TaskStatus.REVOKED,
}


async def enqueue_task(
    queue_name: str, task_name: str, payload: dict[str, Any], priority: int | None = None
) -> str:
    """Publie une tâche Celery sur `queue_name` et retourne son task_id.
    `priority` : si non fourni, retombe sur la priorité par défaut de
    `queue_name` (voir `celery_app.QUEUE_PRIORITIES`, Prompt 6.1) plutôt que
    la priorité neutre de Celery  cohérent avec la table de priorités du
    spec, qui les assigne PAR QUEUE, pas par tâche individuelle."""
    from backend.tasks.celery_app import celery_app, default_priority_for_queue

    effective_priority = priority if priority is not None else default_priority_for_queue(queue_name)

    def _send() -> str:
        result = celery_app.send_task(task_name, kwargs=payload, queue=queue_name, priority=effective_priority)
        return result.id

    task_id = await asyncio.to_thread(_send)
    logger.info(
        "redis_queue.task_enqueued",
        queue=queue_name,
        task_name=task_name,
        task_id=task_id,
        priority=effective_priority,
    )
    return task_id


async def get_task_status(task_id: str) -> TaskStatus:
    from backend.tasks.celery_app import celery_app

    def _fetch_status() -> str:
        return celery_app.AsyncResult(task_id).status

    raw_status = await asyncio.to_thread(_fetch_status)
    status = _CELERY_STATUS_MAP.get(raw_status, TaskStatus.UNKNOWN)
    logger.debug("redis_queue.task_status", task_id=task_id, status=status.value)
    return status


async def cancel_task(task_id: str) -> bool:
    """Révoque une tâche (annulation si encore en attente, terminaison si en cours)."""
    from backend.tasks.celery_app import celery_app

    def _revoke() -> None:
        celery_app.control.revoke(task_id, terminate=True)

    await asyncio.to_thread(_revoke)
    logger.info("redis_queue.task_cancelled", task_id=task_id)
    return True


async def get_queue_length(queue_name: str) -> int:
    """Nombre de tâches en attente sur `queue_name` (lecture directe des
    listes Redis du transport Celery  n'a pas besoin de l'app Celery).

    Résolu au Prompt 6.1 (le piège documenté ci-dessus au moment de
    l'écriture de ce module est maintenant réel : `celery_app.py` active les
    priorités via `broker_transport_options={"priority_steps": ...}`) 
    kombu éclate chaque queue en plusieurs listes Redis suffixées
    `{queue}{sep}{priority}` (priorité 0 = clé non suffixée, `queue_name`
    seul). Somme donc `LLEN` sur `queue_name` ET sur chaque suffixe de
    `celery_app.PRIORITY_STEPS`, plutôt qu'un unique `LLEN` qui
    sous-compterait silencieusement dès qu'une tâche a été publiée à une
    priorité non nulle (le cas de toute queue de ce projet, voir
    `celery_app.QUEUE_PRIORITIES`  aucune n'est à 0)."""
    from backend.tasks.celery_app import KOMBU_REDIS_PRIORITY_SEP, PRIORITY_STEPS

    redis_client = get_redis_client()
    keys = [queue_name] + [f"{queue_name}{KOMBU_REDIS_PRIORITY_SEP}{p}" for p in PRIORITY_STEPS if p != 0]
    lengths = [await redis_client.llen(key) for key in keys]
    total_length = sum(lengths)

    logger.debug("redis_queue.queue_length", queue=queue_name, length=total_length, priority_key_count=len(keys))
    return total_length
