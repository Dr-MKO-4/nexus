"""Router analytics  Prompt 7.1.

KPIs et performances par canal lus depuis PerformanceMetric
(store_metrics_node, agent Analytics)  "KPIs" filtre sur
`channel="cross_channel"` (convention de ce projet pour les métriques
agrégées cross-canal, voir store_metrics_node), "channels" exclut cette même
valeur (ce n'est pas un canal réel, c'est le bucket d'agrégation).

Anomalies lues depuis AgentDecision (decision_type="anomaly_detected") 
persistance ajoutée à store_metrics_node avec ce même prompt (voir
backend/agents/analytics/nodes.py) : avant ce prompt, aucune anomalie
détectée n'était jamais écrite en base.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from backend.api.auth import get_current_user, get_db_session
from backend.db.models.enums import UserRole
from backend.db.models.reports import Report
from backend.db.models.users import User
from backend.db.repositories.performance_repository import AgentDecisionRepository, PerformanceMetricRepository
from backend.db.repositories.report_repository import ReportRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])

_STRICT = ConfigDict(extra="forbid")
_CROSS_CHANNEL = "cross_channel"


class KPIOut(BaseModel):
    model_config = _STRICT

    metric_name: str
    metric_value: float
    period_start: datetime
    period_end: datetime


class ChannelPerformance(BaseModel):
    model_config = _STRICT

    channel: str
    metrics: dict[str, float]


class AnomalyOut(BaseModel):
    model_config = _STRICT

    id: UUID
    decision_data: dict[str, Any]
    outcome: dict[str, Any] | None
    created_at: datetime


class ReportOut(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: UUID
    client_id: UUID
    report_type: str
    period: str | None
    pdf_path: str | None
    delivered_at: datetime | None


class ReportDetailOut(ReportOut):
    content: dict[str, Any]


def _authorize_client_access(current_user: User, client_id: UUID) -> None:
    if current_user.role != UserRole.ADMIN and current_user.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")


def _default_period(period_start: datetime | None, period_end: datetime | None) -> tuple[datetime, datetime]:
    """7 derniers jours par défaut  même fenêtre que celle utilisée par
    store_metrics_node pour écrire les métriques (period_end=now,
    period_start=now-7j), pour que "sans filtre" retrouve bien les valeurs
    écrites par le run le plus récent."""
    end = period_end or datetime.now(timezone.utc)
    start = period_start or (end - timedelta(days=7))
    return start, end


@router.get("/kpis", response_model=list[KPIOut])
async def get_kpis(
    client_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[KPIOut]:
    _authorize_client_access(current_user, client_id)
    start, end = _default_period(period_start, period_end)
    metrics = await PerformanceMetricRepository(session).get_by_client_and_period(client_id, start, end)
    return [
        KPIOut(metric_name=m.metric_name, metric_value=m.metric_value, period_start=m.period_start, period_end=m.period_end)
        for m in metrics
        if m.channel == _CROSS_CHANNEL
    ]


@router.get("/channels", response_model=list[ChannelPerformance])
async def get_channels(
    client_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[ChannelPerformance]:
    _authorize_client_access(current_user, client_id)
    start, end = _default_period(period_start, period_end)
    metrics = await PerformanceMetricRepository(session).get_by_client_and_period(client_id, start, end)

    by_channel: dict[str, dict[str, float]] = defaultdict(dict)
    for m in metrics:
        if m.channel == _CROSS_CHANNEL:
            continue
        by_channel[m.channel][m.metric_name] = m.metric_value

    return [ChannelPerformance(channel=channel, metrics=values) for channel, values in by_channel.items()]


@router.get("/anomalies", response_model=list[AnomalyOut])
async def get_anomalies(
    client_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    since: datetime | None = None,
    limit: int = 50,
) -> list[AnomalyOut]:
    _authorize_client_access(current_user, client_id)
    decisions = await AgentDecisionRepository(session).get_by_type(client_id, "anomaly_detected", since=since, limit=limit)
    return [
        AnomalyOut(id=d.id, decision_data=d.decision_data, outcome=d.outcome, created_at=d.created_at)
        for d in decisions
    ]


@router.get("/reports", response_model=list[ReportOut])
async def list_reports(
    client_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    report_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Report]:
    _authorize_client_access(current_user, client_id)
    return list(await ReportRepository(session).get_by_client(client_id, report_type=report_type, limit=limit, offset=offset))


@router.get("/reports/{report_id}", response_model=ReportDetailOut)
async def get_report(
    report_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> Report:
    report = await ReportRepository(session).get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable.")
    _authorize_client_access(current_user, report.client_id)
    return report


__all__ = ["router"]
