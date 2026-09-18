"""Gestionnaire de budget cross-canal de l'Agent SEA.

`check_daily_pace`/`alert_if_overspending` prennent un budget mensuel et une
dépense à date par campagne  ni `CampaignPerformance` (google_ads.py, pas
de champ budget) ni `CampaignConfig` (state_models.py, pas de champ spend)
ne portent les deux à la fois : `CampaignBudgetInfo` ci-dessous est un
modèle dédié, volontairement minimal, propre à ce module.
"""

import calendar
from datetime import date

import structlog
from pydantic import BaseModel

from backend.core.state.state_models import Alert

logger = structlog.get_logger(__name__)

_PACE_TOLERANCE = 0.15  # +/-15% autour du rythme attendu = "dans le rythme"


class CampaignBudgetInfo(BaseModel):
    campaign_id: str
    monthly_budget: float
    spend_to_date: float


class CampaignPacing(BaseModel):
    campaign_id: str
    expected_spend_to_date: float
    actual_spend_to_date: float
    pace_ratio: float  # actual / expected ; > 1 = dépense plus vite que prévu
    is_on_pace: bool


class PacingStatus(BaseModel):
    campaigns: list[CampaignPacing]
    off_pace_campaign_ids: list[str]
    overall_pace_ratio: float


def calculate_optimal_allocation(total_budget: float, channel_performances: dict[str, float]) -> dict[str, float]:
    """Allocation proportionnelle au ROAS de chaque canal (algorithme simple,
    conforme au spec). Repli en répartition égale si aucun canal n'a de ROAS
    positif connu  évite une division par zéro plutôt que de tout allouer
    au hasard."""
    if not channel_performances:
        return {}

    total_roas = sum(max(0.0, roas) for roas in channel_performances.values())
    if total_roas <= 0:
        share = total_budget / len(channel_performances)
        logger.info("budget_manager.allocation_equal_split", reason="aucun ROAS positif connu")
        return {channel: round(share, 2) for channel in channel_performances}

    allocation = {
        channel: round(total_budget * max(0.0, roas) / total_roas, 2)
        for channel, roas in channel_performances.items()
    }
    logger.info("budget_manager.allocation_computed", allocation=allocation)
    return allocation


def check_daily_pace(campaigns: list[CampaignBudgetInfo]) -> PacingStatus:
    """Compare la dépense à date au rythme attendu (budget mensuel réparti
    linéairement sur le nombre de jours du mois déjà écoulés  pas de
    saisonnalité, volontairement simple, même esprit que
    calculate_optimal_allocation)."""
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    expected_ratio = today.day / days_in_month

    pacings: list[CampaignPacing] = []
    off_pace_ids: list[str] = []
    for campaign in campaigns:
        expected_spend = campaign.monthly_budget * expected_ratio
        pace_ratio = (campaign.spend_to_date / expected_spend) if expected_spend > 0 else 0.0
        is_on_pace = (1 - _PACE_TOLERANCE) <= pace_ratio <= (1 + _PACE_TOLERANCE)
        if not is_on_pace:
            off_pace_ids.append(campaign.campaign_id)
        pacings.append(
            CampaignPacing(
                campaign_id=campaign.campaign_id,
                expected_spend_to_date=round(expected_spend, 2),
                actual_spend_to_date=campaign.spend_to_date,
                pace_ratio=round(pace_ratio, 3),
                is_on_pace=is_on_pace,
            )
        )

    overall_expected = sum(p.expected_spend_to_date for p in pacings)
    overall_actual = sum(p.actual_spend_to_date for p in pacings)
    overall_ratio = round(overall_actual / overall_expected, 3) if overall_expected > 0 else 0.0

    logger.info("budget_manager.pace_checked", campaign_count=len(campaigns), off_pace_count=len(off_pace_ids))
    return PacingStatus(campaigns=pacings, off_pace_campaign_ids=off_pace_ids, overall_pace_ratio=overall_ratio)


def alert_if_overspending(campaigns: list[CampaignBudgetInfo], threshold: float = 0.9) -> list[Alert]:
    """Alerte quand la dépense à date dépasse `threshold` (90% par défaut)
    du budget mensuel TOTAL  distinct de check_daily_pace, qui compare au
    rythme attendu plutôt qu'au budget total : une campagne peut être "dans
    le rythme" (pace_ratio ≈ 1) tout en approchant dangereusement de 100% du
    budget si elle est déjà loin dans le mois."""
    alerts: list[Alert] = []
    for campaign in campaigns:
        if campaign.monthly_budget <= 0:
            continue
        consumed_ratio = campaign.spend_to_date / campaign.monthly_budget
        if consumed_ratio >= threshold:
            alerts.append(
                Alert(
                    level="critical" if consumed_ratio >= 1.0 else "warning",
                    source="sea.budget_manager",
                    message=f"Campagne {campaign.campaign_id} a consommé {consumed_ratio:.0%} de son budget mensuel.",
                    action_required=True,
                )
            )
    logger.info("budget_manager.overspending_check", campaign_count=len(campaigns), alert_count=len(alerts))
    return alerts
