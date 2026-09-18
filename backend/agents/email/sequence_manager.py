"""Gestionnaire de séquences d'emails  Prompt 5.5."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class SequenceConfig(BaseModel):
    model_config = _STRICT_CONFIG

    name: str
    steps_days: list[int]
    description: str


# Séquences prédéfinies (spec Prompt 5.5, offsets en jours depuis le déclenchement).
AVAILABLE_SEQUENCES: dict[str, SequenceConfig] = {
    "welcome": SequenceConfig(name="welcome", steps_days=[0, 2, 5, 10], description="Emails de bienvenue"),
    "nurturing": SequenceConfig(name="nurturing", steps_days=[0, 4, 7, 14, 21], description="Nurturing B2B"),
    "reactivation": SequenceConfig(name="reactivation", steps_days=[0, 7, 14], description="Réactivation des inactifs"),
    "post_purchase": SequenceConfig(name="post_purchase", steps_days=[0, 3, 7], description="Fidélisation post-achat"),
    "cart_abandonment": SequenceConfig(name="cart_abandonment", steps_days=[0, 1, 3], description="Relance panier abandonné"),
}

# Mapping segment -> séquence : couvre les segments produits par
# segmentation.py (engagement, historique d'achat, lead score). Un segment
# absent de cette table retombe sur "nurturing" (repli générique documenté,
# pas une erreur silencieuse  voir get_sequence_for_segment).
_SEGMENT_TO_SEQUENCE: dict[str, str] = {
    # segment_by_engagement
    "high_engagement": "nurturing",
    "medium_engagement": "nurturing",
    "low_engagement": "reactivation",
    "inactive": "reactivation",
    # segment_by_purchase_history
    "new": "welcome",
    "repeat": "post_purchase",
    "high_value": "post_purchase",
    "at_risk": "reactivation",
    "churned": "reactivation",
    # segment_by_lead_score
    "hot": "nurturing",
    "warm": "nurturing",
    "cold": "reactivation",
    # segment explicite hors segmentation.py (ex. déclenché par un événement panier)
    "cart_abandonment": "cart_abandonment",
}
_DEFAULT_SEQUENCE = "nurturing"


def get_sequence_for_segment(segment_name: str) -> SequenceConfig:
    sequence_name = _SEGMENT_TO_SEQUENCE.get(segment_name, _DEFAULT_SEQUENCE)
    if segment_name not in _SEGMENT_TO_SEQUENCE:
        logger.warning("sequence_manager.unknown_segment_fallback", segment_name=segment_name, fallback=_DEFAULT_SEQUENCE)
    return AVAILABLE_SEQUENCES[sequence_name]


async def check_already_received(contact_id: str, sequence_name: str) -> bool:
    """Consulte PostgreSQL (EmailSequenceRepository) pour éviter d'inscrire
    deux fois le même contact dans la même séquence."""
    try:
        from backend.db.repositories.audience_repository import EmailSequenceRepository
        from backend.db.session import get_session

        async with get_session() as session:
            return await EmailSequenceRepository(session).has_received_sequence(UUID(contact_id), sequence_name)
    except Exception as exc:
        logger.warning("sequence_manager.check_already_received_failed", contact_id=contact_id, sequence_name=sequence_name, error=str(exc))
        # Par prudence, en cas d'indisponibilité de la DB on considère que le
        # contact n'a PAS encore reçu la séquence plutôt que de bloquer tout
        # envoi  un doublon occasionnel est moins coûteux qu'une séquence
        # jamais déclenchée.
        return False


def calculate_next_send_time(step: int, optimal_hour: int) -> datetime:
    """`step` : offset en jours depuis le déclenchement de la séquence (ex.
    0, 2, 5, 10 pour "welcome"). `optimal_hour` : heure locale (0-23)
    privilégiée pour l'envoi (cohérent avec `scheduler.get_optimal_slots` de
    l'Agent Social, même logique appliquée au canal email)."""
    if not 0 <= optimal_hour <= 23:
        raise ValueError(f"optimal_hour doit être entre 0 et 23, reçu {optimal_hour}")

    now = datetime.now(timezone.utc)
    candidate = (now + timedelta(days=step)).replace(hour=optimal_hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


__all__ = ["SequenceConfig", "AVAILABLE_SEQUENCES", "get_sequence_for_segment", "check_already_received", "calculate_next_send_time"]
