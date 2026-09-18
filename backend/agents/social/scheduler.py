"""Planificateur de publications intelligent  Prompt 5.4."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.core.state.state_models import Content

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

_MIN_GAP_MINUTES = 60

# Créneaux par défaut (heures locales) quand aucun historique d'engagement
# n'est disponible pour le client  usages courants par plateforme,
# documentés comme repli explicite, pas une donnée mesurée.
_DEFAULT_HOURS_BY_PLATFORM: dict[str, list[int]] = {
    "linkedin": [8, 12, 17],
    "meta": [11, 14, 19],
    "tiktok": [19, 21, 22],
}
_DEFAULT_FALLBACK_HOURS = [9, 13, 18]


class CalendarEntry(BaseModel):
    model_config = _STRICT_CONFIG

    content_id: str
    platform: str
    scheduled_at: datetime


class PublicationCalendar(BaseModel):
    model_config = _STRICT_CONFIG

    period: str
    entries: list[CalendarEntry] = Field(default_factory=list)


async def get_optimal_slots(platform: str, client_id: str, num_slots: int) -> list[datetime]:
    """Créneaux optimaux basés sur l'historique d'engagement (PostgreSQL,
    PerformanceMetric channel=platform, metric_name="engagement_rate") :
    heures de la journée qui reviennent le plus souvent parmi les mesures à
    forte valeur. Repli sur des créneaux par défaut documentés si
    l'historique est vide ou indisponible."""
    best_hours: list[int] = []
    try:
        from backend.db.repositories.performance_repository import PerformanceMetricRepository
        from backend.db.session import get_session

        async with get_session() as session:
            metrics = await PerformanceMetricRepository(session).get_by_channel_and_period(
                UUID(client_id),
                platform,
                datetime.now(timezone.utc) - timedelta(days=90),
                datetime.now(timezone.utc),
            )
        engagement_metrics = [m for m in metrics if m.metric_name == "engagement_rate"]
        if engagement_metrics:
            hour_scores: Counter[int] = Counter()
            for metric in engagement_metrics:
                hour_scores[metric.period_start.hour] += metric.metric_value
            best_hours = [hour for hour, _ in hour_scores.most_common(num_slots)]
    except Exception as exc:
        logger.warning("scheduler.optimal_slots_history_failed", client_id=client_id, platform=platform, error=str(exc))

    if not best_hours:
        best_hours = _DEFAULT_HOURS_BY_PLATFORM.get(platform, _DEFAULT_FALLBACK_HOURS)

    now = datetime.now(timezone.utc)
    slots: list[datetime] = []
    day_offset = 0
    while len(slots) < num_slots:
        hour = best_hours[len(slots) % len(best_hours)]
        candidate = (now + timedelta(days=day_offset)).replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            slots.append(candidate)
        if len(slots) % len(best_hours) == 0:
            day_offset += 1

    logger.info("scheduler.optimal_slots_computed", client_id=client_id, platform=platform, slot_count=len(slots))
    return slots[:num_slots]


def avoid_conflicts(
    schedule: list[datetime], existing_publications: list[datetime], min_gap_minutes: int = _MIN_GAP_MINUTES
) -> list[datetime]:
    """Décale chaque créneau proposé qui tombe à moins de `min_gap_minutes`
    d'une publication existante, par pas de `min_gap_minutes`, jusqu'à
    trouver un créneau libre."""
    min_gap = timedelta(minutes=min_gap_minutes)
    adjusted: list[datetime] = []
    occupied = list(existing_publications)

    for slot in schedule:
        candidate = slot
        while any(abs((candidate - other).total_seconds()) < min_gap.total_seconds() for other in occupied):
            candidate = candidate + min_gap
        adjusted.append(candidate)
        occupied.append(candidate)

    return adjusted


def distribute_content_calendar(contents: list[Content], period: str) -> PublicationCalendar:
    """Répartit uniformément les contenus fournis sur la période donnée
    ("7d", "30d", ...), un créneau par jour dans l'ordre des contenus, en
    reprenant le créneau par défaut de leur plateforme."""
    if not period.endswith("d"):
        raise ValueError(f"Format de période non supporté : {period!r} (attendu ex. '7d', '30d')")
    days = int(period[:-1])

    if not contents:
        return PublicationCalendar(period=period, entries=[])

    now = datetime.now(timezone.utc)
    interval_days = max(days / len(contents), 1) if len(contents) <= days else days / len(contents)

    entries: list[CalendarEntry] = []
    for index, content in enumerate(contents):
        hours = _DEFAULT_HOURS_BY_PLATFORM.get(content.platform, _DEFAULT_FALLBACK_HOURS)
        scheduled_at = (now + timedelta(days=index * interval_days)).replace(
            hour=hours[0], minute=0, second=0, microsecond=0
        )
        entries.append(CalendarEntry(content_id=content.id, platform=content.platform, scheduled_at=scheduled_at))

    logger.info("scheduler.calendar_distributed", period=period, content_count=len(contents))
    return PublicationCalendar(period=period, entries=entries)


__all__ = ["CalendarEntry", "PublicationCalendar", "get_optimal_slots", "avoid_conflicts", "distribute_content_calendar"]
