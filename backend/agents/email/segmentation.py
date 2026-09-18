"""Moteur de segmentation comportementale  Prompt 5.5.

Opère sur `backend.tools.email.mautic_client.Contact` (la forme Mautic,
utilisée aussi bien pour les contacts chargés depuis PostgreSQL que ceux
récupérés via l'API Mautic  voir `agents.email.nodes.load_email_context_node`).
"""

from datetime import datetime, timezone

import structlog

from backend.tools.email.mautic_client import Contact

logger = structlog.get_logger(__name__)

# Seuils de récence (jours depuis la dernière interaction) pour
# segment_by_engagement  choix documenté, pas une donnée mesurée.
_HIGH_ENGAGEMENT_DAYS = 7
_MEDIUM_ENGAGEMENT_DAYS = 30
_LOW_ENGAGEMENT_DAYS = 90

# Seuils pour segment_by_purchase_history (lus depuis Contact.behavior_data :
# "purchase_count", "total_spent", "days_since_last_purchase")  un contact
# sans aucune donnée d'achat n'entre dans aucun de ces segments.
_HIGH_VALUE_SPEND_THRESHOLD = 500.0
_AT_RISK_DAYS_SINCE_PURCHASE = 60
_CHURNED_DAYS_SINCE_PURCHASE = 180


def _parse_last_interaction(contact: Contact) -> datetime | None:
    if not contact.last_interaction_at:
        return None
    try:
        return datetime.fromisoformat(contact.last_interaction_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def segment_by_engagement(contacts: list[Contact]) -> dict[str, list[Contact]]:
    """Segments : high_engagement, medium_engagement, low_engagement, inactive
     basé sur la récence de `last_interaction_at`."""
    segments: dict[str, list[Contact]] = {
        "high_engagement": [],
        "medium_engagement": [],
        "low_engagement": [],
        "inactive": [],
    }
    now = datetime.now(timezone.utc)

    for contact in contacts:
        last_interaction = _parse_last_interaction(contact)
        if last_interaction is None:
            segments["inactive"].append(contact)
            continue
        days_since = (now - last_interaction).days
        if days_since <= _HIGH_ENGAGEMENT_DAYS:
            segments["high_engagement"].append(contact)
        elif days_since <= _MEDIUM_ENGAGEMENT_DAYS:
            segments["medium_engagement"].append(contact)
        elif days_since <= _LOW_ENGAGEMENT_DAYS:
            segments["low_engagement"].append(contact)
        else:
            segments["inactive"].append(contact)

    logger.info("segmentation.by_engagement", **{k: len(v) for k, v in segments.items()})
    return segments


def segment_by_purchase_history(contacts: list[Contact]) -> dict[str, list[Contact]]:
    """Segments : new, repeat, high_value, at_risk, churned  basé sur
    `behavior_data`. Priorité (un contact n'apparaît que dans un seul
    segment) : churned > at_risk > high_value > repeat > new, du signal le
    plus critique au plus générique."""
    segments: dict[str, list[Contact]] = {"new": [], "repeat": [], "high_value": [], "at_risk": [], "churned": []}

    for contact in contacts:
        purchase_count = int(contact.behavior_data.get("purchase_count", 0) or 0)
        if purchase_count == 0:
            continue  # aucun signal d'achat -> hors de ce segmenteur (pas "new" par défaut)

        total_spent = float(contact.behavior_data.get("total_spent", 0.0) or 0.0)
        days_since_purchase = contact.behavior_data.get("days_since_last_purchase")
        days_since_purchase = int(days_since_purchase) if days_since_purchase is not None else None

        if days_since_purchase is not None and days_since_purchase >= _CHURNED_DAYS_SINCE_PURCHASE:
            segments["churned"].append(contact)
        elif days_since_purchase is not None and days_since_purchase >= _AT_RISK_DAYS_SINCE_PURCHASE:
            segments["at_risk"].append(contact)
        elif total_spent >= _HIGH_VALUE_SPEND_THRESHOLD:
            segments["high_value"].append(contact)
        elif purchase_count > 1:
            segments["repeat"].append(contact)
        else:
            segments["new"].append(contact)

    logger.info("segmentation.by_purchase_history", **{k: len(v) for k, v in segments.items()})
    return segments


def segment_by_lead_score(contacts: list[Contact], threshold: int = 50) -> dict[str, list[Contact]]:
    """Segments : hot, warm, cold  cold : score < threshold ; warm :
    threshold <= score < 80 ; hot : score >= 80."""
    segments: dict[str, list[Contact]] = {"hot": [], "warm": [], "cold": []}
    for contact in contacts:
        if contact.lead_score >= 80:
            segments["hot"].append(contact)
        elif contact.lead_score >= threshold:
            segments["warm"].append(contact)
        else:
            segments["cold"].append(contact)

    logger.info("segmentation.by_lead_score", threshold=threshold, **{k: len(v) for k, v in segments.items()})
    return segments


_OPERATORS = {
    "gte": lambda value, target: value is not None and value >= target,
    "lte": lambda value, target: value is not None and value <= target,
    "gt": lambda value, target: value is not None and value > target,
    "lt": lambda value, target: value is not None and value < target,
    "contains": lambda value, target: target in (value or []),
    "eq": lambda value, target: value == target,
}


def _resolve_field(contact: Contact, field: str):
    if hasattr(contact, field):
        return getattr(contact, field)
    return contact.behavior_data.get(field)


def build_custom_segment(contacts: list[Contact], rules: dict) -> list[Contact]:
    """Filtre `contacts` selon `rules`, un dict de `{"champ__operateur":
    valeur}` (opérateurs : gte/lte/gt/lt/contains/eq  eq est le défaut si
    aucun suffixe `__operateur` n'est présent). `champ` cherche d'abord un
    attribut de Contact (ex. "lead_score", "opted_out"), sinon une clé de
    `behavior_data`. Toutes les règles doivent être satisfaites (ET logique)."""
    matched: list[Contact] = []
    for contact in contacts:
        ok = True
        for rule_key, target in rules.items():
            if "__" in rule_key:
                field, operator = rule_key.rsplit("__", 1)
            else:
                field, operator = rule_key, "eq"
            if operator not in _OPERATORS:
                raise ValueError(f"Opérateur de règle inconnu : {operator!r} (règle {rule_key!r})")
            value = _resolve_field(contact, field)
            if not _OPERATORS[operator](value, target):
                ok = False
                break
        if ok:
            matched.append(contact)

    logger.info("segmentation.custom_segment", rule_count=len(rules), matched_count=len(matched))
    return matched


__all__ = ["segment_by_engagement", "segment_by_purchase_history", "segment_by_lead_score", "build_custom_segment"]
