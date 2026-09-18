"""Configuration Celery principale  Prompt 6.1.

Priorités par queue (spec)  INVERSION CONFIRMÉE du transport Redis de
kombu, vérifiée par lecture directe du code source installé (`kombu==5.5.4`,
`kombu.transport.redis.Channel`), pas supposée :

- `Channel.priority(n)` mappe une priorité arbitraire vers la valeur la plus
  proche dans `priority_steps` via `bisect()`, qui EXIGE `priority_steps`
  trié ASCENDANT pour fonctionner correctement.
- `Channel._brpop_start()` construit la liste de clés `BRPOP` en itérant
  `priority_steps` dans CET ORDRE (ascendant) : `[_q_for_pri(q, p) for p in
  priority_steps for q in queues]`. Redis `BRPOP` retourne la première clé
  non vide dans l'ordre de la liste fournie.
- Conséquence directe, vérifiée en reproduisant l'ordre des clés généré :
  **la valeur de priorité la plus BASSE (0) est vérifiée EN PREMIER et donc
  traitée en premier** ; la plus haute (10) est vérifiée en dernier.
  C'est l'INVERSE de la convention "priority 10 = critique" du spec.

Résolu ci-dessous : `QUEUE_PRIORITIES` garde les valeurs SÉMANTIQUES du spec
(10 = le plus important, cohérent avec la lecture métier de "orchestration :
priority 10 (critique)"), et `default_priority_for_queue()` les convertit en
priorité kombu réelle (`kombu_priority = max(PRIORITY_STEPS) - priorité
métier`) avant tout appel `send_task(priority=...)`  sans cette conversion,
`orchestration` (métier 10) aurait été la queue la MOINS prioritaire en
pratique, l'inverse exact de l'intention du spec.
"""

from celery import Celery

from backend.config.settings import settings

# ── Queues et priorités (spec Prompt 6.1) ───────────────────────────────────
# Réutilise les constantes déjà définies dans tasks/queues/redis_queue.py
# (Prompt 4.x, écrit avant ce module) plutôt que de les redéfinir ici.
from backend.tasks.queues.redis_queue import (
    QUEUE_ANALYTICS,
    QUEUE_EMAIL,
    QUEUE_IMAGE,
    QUEUE_LLM,
    QUEUE_ORCHESTRATION,
    QUEUE_SEO,
    QUEUE_SOCIAL,
)

QUEUE_PRIORITIES: dict[str, int] = {
    QUEUE_ORCHESTRATION: 10,
    QUEUE_LLM: 9,
    QUEUE_IMAGE: 5,
    QUEUE_EMAIL: 5,
    QUEUE_SOCIAL: 5,
    QUEUE_ANALYTICS: 3,
    QUEUE_SEO: 2,
}

# Valeurs de priorité valides pour le transport Redis de kombu  doit couvrir
# toutes les valeurs de QUEUE_PRIORITIES (0 = non prioritaire/défaut, jusqu'à
# la priorité la plus haute utilisée, 10).
PRIORITY_STEPS: list[int] = list(range(11))

# Séparateur utilisé par kombu pour suffixer les clés Redis par priorité
# (`{queue}{sep}{priority}`, priorité 0 = clé non suffixée)  dupliqué ici et
# dans redis_queue.py plutôt qu'importé depuis kombu (implémentation interne,
# non exposée comme API publique stable).
KOMBU_REDIS_PRIORITY_SEP = "\x06\x16"


def default_priority_for_queue(queue_name: str) -> int:
    """Priorité kombu RÉELLE (pas la priorité métier du spec) pour une queue
    nommée  utilisée par `redis_queue.enqueue_task` quand l'appelant ne
    fixe pas explicitement de priorité par tâche. Convertit la valeur
    sémantique de `QUEUE_PRIORITIES` (10 = le plus important) en valeur
    kombu réelle (0 = traité en premier  voir docstring de module pour la
    preuve de cette inversion). Queue absente de la table du spec (ex.
    future queue ad hoc) -> priorité métier neutre = 0 -> priorité kombu =
    `max(PRIORITY_STEPS)` (la moins urgente, un repli sûr par défaut)."""
    business_priority = QUEUE_PRIORITIES.get(queue_name, 0)
    return max(PRIORITY_STEPS) - business_priority


celery_app = Celery(
    "nexus",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # Sérialisation : JSON par défaut, msgpack accepté en plus pour les gros
    # payloads (ex. image_worker.py  un base64 d'image en JSON gonfle
    # significativement la taille du message ; msgpack reste compact)  les
    # tâches individuelles choisissent leur sérialiseur via
    # `.apply_async(serializer="msgpack")`, la config globale ne fait
    # qu'autoriser les deux côté réception.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json", "msgpack"],
    # Fiabilité : ack après exécution complète (pas avant), un seul message
    # prefetch par worker (évite qu'un worker lent accapare une tâche qu'un
    # worker libre aurait pu prendre  "starvation" au sens du spec).
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Budget de temps par tâche.
    task_time_limit=600,
    task_soft_time_limit=540,
    # Retry avec backoff exponentiel (appliqué par défaut à toute tâche
    # `bind=True` qui lève et ne gère pas elle-même son propre retry  voir
    # workers/*.py pour les stratégies de retry spécifiques par type
    # d'erreur, plus fines que ce défaut générique).
    task_autoretry_for=(Exception,),
    task_retry_backoff=True,
    task_retry_backoff_max=600,
    task_retry_jitter=True,
    task_max_retries=5,
    # Priorités (transport Redis, voir docstring de module pour la preuve de
    # l'inversion business->kombu). `task_default_priority` s'applique à
    # toute tâche envoyée SANS `priority=` explicite (ex. les tâches de
    # maintenance de scheduled_tasks.py, sans queue/priorité dédiée)  fixé
    # à la valeur kombu la MOINS urgente (`max(PRIORITY_STEPS)`, pas `0`,
    # qui serait au contraire la PLUS urgente sous cette inversion) pour
    # qu'une tâche non explicitement priorisée ne double jamais celles qui
    # le sont.
    task_queue_max_priority=max(PRIORITY_STEPS),
    task_default_priority=max(PRIORITY_STEPS),
    broker_transport_options={
        "priority_steps": PRIORITY_STEPS,
        "sep": KOMBU_REDIS_PRIORITY_SEP,
        "queue_order_strategy": "priority",
    },
    # Découverte des tâches définies dans workers/*.py  imports différés par
    # Celery lui-même via `autodiscover_tasks`, pas ici (évite un import
    # circulaire avec ce module au chargement).
    imports=(
        "backend.tasks.workers.llm_worker",
        "backend.tasks.workers.image_worker",
        "backend.tasks.workers.marketing_worker",
    ),
    timezone="UTC",
    enable_utc=True,
)

# Celery Beat (tâches périodiques)  défini dans scheduled_tasks.py, qui
# peuple `celery_app.conf.beat_schedule` à l'import (voir ce fichier).

__all__ = ["celery_app", "QUEUE_PRIORITIES", "PRIORITY_STEPS", "KOMBU_REDIS_PRIORITY_SEP", "default_priority_for_queue"]
