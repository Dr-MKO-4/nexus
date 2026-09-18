"""Constructeur de rapports structurés  Prompt 5.8."""

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class KPIResult(BaseModel):
    model_config = _STRICT_CONFIG

    name: str
    value: float
    target: Optional[float] = None
    trend: Optional[Literal["up", "down", "stable"]] = None


class ChannelReport(BaseModel):
    model_config = _STRICT_CONFIG

    channel: str
    spend: float = 0.0
    revenue: float = 0.0
    roas: float = 0.0
    conversions: float = 0.0
    summary: str = ""


class ContentPerformance(BaseModel):
    model_config = _STRICT_CONFIG

    content_id: str
    title: Optional[str] = None
    platform: str
    engagement_score: float = 0.0
    views: int = 0


class AnomalyReport(BaseModel):
    model_config = _STRICT_CONFIG

    score: float
    explanation: str
    severity: Literal["low", "medium", "high"] = "medium"


class DecisionLog(BaseModel):
    model_config = _STRICT_CONFIG

    agent: str
    decision_type: str
    timestamp: datetime
    summary: str


class Recommendation(BaseModel):
    model_config = _STRICT_CONFIG

    action: str
    expected_impact: str
    effort: Literal["low", "medium", "high"] = "medium"
    priority: int = Field(default=3, ge=1, le=5)


class BudgetSummary(BaseModel):
    model_config = _STRICT_CONFIG

    total_budget: float = 0.0
    total_spend: float = 0.0
    remaining: float = 0.0
    utilization_pct: float = 0.0


class WeeklyReport(BaseModel):
    model_config = _STRICT_CONFIG

    period: str
    client_id: str
    executive_summary: str
    kpi_scorecard: dict[str, KPIResult] = Field(default_factory=dict)
    channel_performance: dict[str, ChannelReport] = Field(default_factory=dict)
    top_contents: list[ContentPerformance] = Field(default_factory=list)
    anomalies_detected: list[AnomalyReport] = Field(default_factory=list)
    decisions_taken: list[DecisionLog] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    budget_summary: BudgetSummary = Field(default_factory=BudgetSummary)
    next_week_plan: str = ""


class CampaignReport(BaseModel):
    model_config = _STRICT_CONFIG

    campaign_id: str
    period: str
    kpis: dict[str, KPIResult] = Field(default_factory=dict)
    summary: str = ""


class CrisisReport(BaseModel):
    model_config = _STRICT_CONFIG

    crisis_id: str
    detected_at: datetime
    severity: Literal["low", "medium", "high", "critical"]
    summary: str
    actions_taken: list[str] = Field(default_factory=list)
    resolved: bool = False


def _kpi_scorecard_from_dict(kpis: dict) -> dict[str, KPIResult]:
    scorecard: dict[str, KPIResult] = {}
    for name, value in kpis.items():
        try:
            scorecard[name] = KPIResult(name=name, value=float(value))
        except (TypeError, ValueError):
            # Valeur non numérique (ex. inf déjà neutralisé en amont par
            # Analytics, mais défense en profondeur ici aussi)  ignorée
            # plutôt que de faire échouer tout le scorecard pour un seul KPI.
            logger.warning("report_builder.kpi_skipped_non_numeric", kpi_name=name, value=value)
    return scorecard


def build_weekly_report(analytics_data: dict, decisions: list[dict], kpis: dict) -> WeeklyReport:
    """Assemble un `WeeklyReport` depuis les données brutes déjà collectées
    (analytics_data : sortie de l'Agent Analytics  kpis/anomalies/attribution/
    insights ; decisions : lignes AgentDecision ; kpis : dict plat déjà
    calculé, peut recouper analytics_data["kpis"]  les deux sont acceptés
    séparément pour matcher la signature imposée par le spec)."""
    period = analytics_data.get("period") or datetime.now(timezone.utc).strftime("%Y-W%V")
    client_id = analytics_data.get("client_id", "")

    merged_kpis = {**(analytics_data.get("kpis") or {}), **(kpis or {})}
    kpi_scorecard = _kpi_scorecard_from_dict(merged_kpis)

    anomalies_detected = [
        AnomalyReport(
            score=a.get("score", 0.0),
            explanation=a.get("explanation_clear") or a.get("explanation", ""),
            severity="high" if a.get("score", 0.0) > 0.8 else "medium",
        )
        for a in (analytics_data.get("anomalies") or [])
    ]

    decisions_taken = [
        DecisionLog(
            agent=d.get("agent_name", d.get("agent", "unknown")),
            decision_type=d.get("decision_type", "unknown"),
            timestamp=d.get("created_at") or datetime.now(timezone.utc),
            summary=json_summary(d.get("decision_data") or {}),
        )
        for d in decisions
    ]

    recommendations = [
        Recommendation(
            action=r.get("action", ""),
            expected_impact=r.get("expected_impact", ""),
            effort=r.get("effort", "medium"),
            priority=r.get("priority", 3),
        )
        for r in (analytics_data.get("recommendations") or [])
    ]

    # channel_performance/top_contents/budget_summary/next_week_plan : le
    # spec fixe la signature à 3 paramètres (analytics_data, decisions,
    # kpis)  ces champs, produits par des nœuds distincts du graphe
    # Reporting (generate_channel_breakdown_node, format_report_node), sont
    # donc transmis DANS analytics_data plutôt que comme paramètres séparés,
    # au lieu de rester silencieusement vides dans le WeeklyReport final.
    channel_performance = {
        name: ChannelReport(**data) if not isinstance(data, ChannelReport) else data
        for name, data in (analytics_data.get("channel_performance") or {}).items()
    }
    top_contents = [
        ContentPerformance(**c) if not isinstance(c, ContentPerformance) else c
        for c in (analytics_data.get("top_contents") or [])
    ]
    budget_data = analytics_data.get("budget_summary") or {}
    budget_summary = BudgetSummary(**budget_data) if budget_data else BudgetSummary()

    report = WeeklyReport(
        period=period,
        client_id=client_id,
        executive_summary=analytics_data.get("executive_summary", ""),
        kpi_scorecard=kpi_scorecard,
        channel_performance=channel_performance,
        top_contents=top_contents,
        anomalies_detected=anomalies_detected,
        decisions_taken=decisions_taken,
        recommendations=recommendations,
        budget_summary=budget_summary,
        next_week_plan=analytics_data.get("next_week_plan", ""),
    )
    logger.info("report_builder.weekly_report_built", client_id=client_id, period=period)
    return report


def json_summary(data: dict, max_len: int = 200) -> str:
    """Résumé textuel court d'un dict de décision (`AgentDecision.decision_data`),
    pour `DecisionLog.summary`  pas de format canonique imposé par le spec."""
    import json

    text = json.dumps(data, ensure_ascii=False, default=str)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


async def build_campaign_report(campaign_id: str) -> CampaignReport:
    """Construit un rapport de campagne depuis les PerformanceMetric
    stockées (PostgreSQL)."""
    kpis: dict[str, KPIResult] = {}
    try:
        from backend.db.repositories.performance_repository import PerformanceMetricRepository
        from backend.db.session import get_session

        async with get_session() as session:
            metrics = await PerformanceMetricRepository(session).get_by_campaign(UUID(campaign_id))
        for metric in metrics:
            kpis[metric.metric_name] = KPIResult(name=metric.metric_name, value=metric.metric_value)
    except Exception as exc:
        logger.warning("report_builder.campaign_report_metrics_failed", campaign_id=campaign_id, error=str(exc))

    period = datetime.now(timezone.utc).strftime("%Y-W%V")
    summary = f"{len(kpis)} métrique(s) disponible(s) pour cette campagne." if kpis else "Aucune métrique disponible pour cette campagne."
    logger.info("report_builder.campaign_report_built", campaign_id=campaign_id, kpi_count=len(kpis))
    return CampaignReport(campaign_id=campaign_id, period=period, kpis=kpis, summary=summary)


# Les producteurs amont de `crisis_data` n'utilisent pas tous le même
# vocabulaire de sévérité : `Alert.level` (state_models.py, utilisé par
# agents.social.nodes.crisis_detector_node) est "info"|"warning"|"critical",
# tandis que `CrisisReport.severity` (ce module) est
# "low"|"medium"|"high"|"critical"  build_crisis_report accepte un
# `crisis_data` générique (le spec ne fixe aucun schéma amont précis), donc
# une normalisation est nécessaire pour ne jamais lever sur une valeur
# légitime mais dans l'autre vocabulaire.
_SEVERITY_NORMALIZATION = {
    "info": "low",
    "warning": "medium",
    "critical": "critical",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


def build_crisis_report(crisis_data: dict) -> CrisisReport:
    """Construit un rapport de crise depuis les données produites par
    crisis_detector (Agent Social) ou handle_crisis (Orchestrateur)."""
    from uuid import uuid4

    raw_severity = str(crisis_data.get("severity") or crisis_data.get("level") or "medium").lower()
    severity = _SEVERITY_NORMALIZATION.get(raw_severity, "medium")
    if raw_severity not in _SEVERITY_NORMALIZATION:
        logger.warning("report_builder.unknown_severity_defaulted", raw_severity=raw_severity)

    report = CrisisReport(
        crisis_id=crisis_data.get("crisis_id") or str(uuid4()),
        detected_at=crisis_data.get("detected_at") or datetime.now(timezone.utc),
        severity=severity,
        summary=crisis_data.get("summary", crisis_data.get("message", "")),
        actions_taken=crisis_data.get("actions_taken", []),
        resolved=crisis_data.get("resolved", False),
    )
    logger.info("report_builder.crisis_report_built", crisis_id=report.crisis_id, severity=report.severity)
    return report


__all__ = [
    "KPIResult",
    "ChannelReport",
    "ContentPerformance",
    "AnomalyReport",
    "DecisionLog",
    "Recommendation",
    "BudgetSummary",
    "WeeklyReport",
    "CampaignReport",
    "CrisisReport",
    "build_weekly_report",
    "build_campaign_report",
    "build_crisis_report",
]
