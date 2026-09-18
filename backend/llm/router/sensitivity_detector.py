"""Détecteur de sensibilité des données : première étape de la logique de
routage de HybridRouter (backend/llm/router/hybrid_router.py)  une tâche
sensible est TOUJOURS forcée en inférence locale, quelle que soit la charge
GPU ou le budget restant.
"""

import re

import structlog

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

# Motifs génériques indicateurs de données personnelles/sensibles dans le
# texte de la tâche elle-même, au-delà des task_type explicitement listés
# dans settings.HYBRID_SENSITIVE_TASKS.
_SENSITIVE_KEYWORD_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(mot\s?de\s?passe|password|identifiant|credentials?)\b", re.IGNORECASE),
    re.compile(r"\b(carte\s?bancaire|numéro\s?de\s?carte|cvv|iban|rib)\b", re.IGNORECASE),
    re.compile(r"\b(numéro\s?de\s?sécurité\s?sociale|ssn|passeport|carte\s?d['e]identité)\b", re.IGNORECASE),
    re.compile(r"\b(données?\s?médicales?|dossier\s?médical|diagnostic)\b", re.IGNORECASE),
    re.compile(r"\b(données?\s?clients?|données?\s?personnelles?|\bpii\b|rgpd|gdpr)\b", re.IGNORECASE),
]

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def is_sensitive(task_description: str, task_type: str | None = None) -> bool:
    """Détermine si une tâche doit être forcée en inférence locale.

    Deux sources de signal, combinées en OU (une seule suffit) :
    1. `task_type` figure explicitement dans settings.HYBRID_SENSITIVE_TASKS.
    2. Le texte de la tâche contient un motif sensible (mots-clés ou email).
    """
    reasons: list[str] = []

    sensitive_task_types = {t.lower() for t in settings.HYBRID_SENSITIVE_TASKS}
    if task_type and task_type.lower() in sensitive_task_types:
        reasons.append(f"task_type={task_type!r} listé dans HYBRID_SENSITIVE_TASKS")

    for pattern in _SENSITIVE_KEYWORD_PATTERNS:
        if pattern.search(task_description):
            reasons.append(f"motif sensible détecté ({pattern.pattern!r})")
            break

    if _EMAIL_PATTERN.search(task_description):
        reasons.append("adresse email détectée dans le texte de la tâche")

    sensitive = bool(reasons)
    logger.info(
        "sensitivity_detector.decision",
        task_type=task_type,
        sensitive=sensitive,
        reasons=reasons,
    )
    return sensitive
