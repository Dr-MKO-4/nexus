"""Définition des files d'attente de tâches (par agent, par priorité)."""

from backend.tasks.queues.redis_queue import (
    QUEUE_ANALYTICS,
    QUEUE_EMAIL,
    QUEUE_IMAGE,
    QUEUE_LLM,
    QUEUE_ORCHESTRATION,
    QUEUE_SEO,
    QUEUE_SOCIAL,
    TaskStatus,
    cancel_task,
    enqueue_task,
    get_queue_length,
    get_task_status,
)

__all__ = [
    "QUEUE_ORCHESTRATION",
    "QUEUE_LLM",
    "QUEUE_IMAGE",
    "QUEUE_EMAIL",
    "QUEUE_SOCIAL",
    "QUEUE_ANALYTICS",
    "QUEUE_SEO",
    "TaskStatus",
    "enqueue_task",
    "get_task_status",
    "cancel_task",
    "get_queue_length",
]
