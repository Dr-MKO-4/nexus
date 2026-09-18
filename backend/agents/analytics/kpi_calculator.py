"""Calculateur de KPIs marketing  Prompt 5.6."""

from datetime import datetime, timezone
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

AttributionAlgorithm = Literal["last_click", "first_click", "linear", "time_decay"]
# Demi-vie (en "rangs" de touchpoint, du plus ancien au plus récent) pour
# time_decay  choix documenté faute de timestamps réels systématiquement
# disponibles sur les touchpoints (voir multi_touch_attribution).
_TIME_DECAY_HALF_LIFE = 2.0


class WeeklyScorecard(BaseModel):
    model_config = _STRICT_CONFIG

    period: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cac: float | None = None
    ltv: float | None = None
    roas: float | None = None
    cpa: float | None = None
    email_roi: float | None = None
    organic_traffic_growth: float | None = None


def calculate_cac(ad_spend: float, new_customers: float) -> float:
    """Coût d'acquisition client. 0.0 si aucun nouveau client (plutôt qu'une
    division par zéro)  un CAC est indéfini sans acquisition, 0.0 signale
    "pas de coût constaté" au niveau de l'appelant plutôt que de lever."""
    if new_customers <= 0:
        return 0.0
    return ad_spend / new_customers


def calculate_ltv(avg_purchase: float, frequency: float, margin: float, churn_rate: float) -> float:
    """Customer Lifetime Value = (panier moyen x fréquence d'achat x marge) /
    taux de churn. `churn_rate` doit être > 0 (un churn de 0 rendrait la LTV
    mathématiquement infinie, pas une valeur numérique valide)  lève
    ValueError plutôt que de renvoyer un 0.0 ou un inf trompeur."""
    if churn_rate <= 0:
        raise ValueError(f"churn_rate doit être > 0 pour une LTV définie, reçu {churn_rate}")
    return (avg_purchase * frequency * margin) / churn_rate


def calculate_roas(revenue: float, ad_spend: float) -> float:
    """Return on Ad Spend. 0.0 si aucune dépense publicitaire."""
    if ad_spend <= 0:
        return 0.0
    return revenue / ad_spend


def calculate_cpa(total_cost: float, conversions: float) -> float:
    """Coût par acquisition. 0.0 si aucune conversion."""
    if conversions <= 0:
        return 0.0
    return total_cost / conversions


def calculate_email_roi(revenue: float, costs: float) -> float:
    """ROI email = (revenu - coûts) / coûts. 0.0 si aucun coût constaté."""
    if costs <= 0:
        return 0.0
    return (revenue - costs) / costs


def calculate_organic_traffic_growth(current: float, previous: float) -> float:
    """Croissance du trafic organique = (actuel - précédent) / précédent.
    Si `previous` est 0 : croissance "infinie" si du trafic est apparu
    (retourne float('inf'), un signal légitime distinct de "pas de
    croissance"), 0.0 si les deux valent 0 (rien à comparer)."""
    if previous <= 0:
        return float("inf") if current > 0 else 0.0
    return (current - previous) / previous


def multi_touch_attribution(
    touchpoints: list[dict], conversion_value: float, algorithm: AttributionAlgorithm = "linear"
) -> dict[str, float]:
    """Répartit `conversion_value` entre les canaux des `touchpoints`
    (chronologiques, `touchpoints[0]` = premier contact, `[-1]` = dernier
    avant conversion ; chaque touchpoint : `{"channel": str}`).

    `algorithm` : paramètre ajouté au-delà de la signature à 2 arguments
    littérale du spec  nécessaire pour sélectionner entre les 4 algorithmes
    qu'il énumère (last_click/first_click/linear/time_decay), sinon ces noms
    seraient purement documentaires sans jamais être atteignables. Défaut
    "linear", le plus neutre des quatre.
    """
    if not touchpoints:
        return {}

    channels = [tp["channel"] for tp in touchpoints]
    attribution: dict[str, float] = {}

    if algorithm == "last_click":
        attribution[channels[-1]] = conversion_value
    elif algorithm == "first_click":
        attribution[channels[0]] = conversion_value
    elif algorithm == "linear":
        share = conversion_value / len(channels)
        for channel in channels:
            attribution[channel] = attribution.get(channel, 0.0) + share
    elif algorithm == "time_decay":
        # Poids exponentiel croissant du premier au dernier touchpoint
        # (le plus récent avant conversion pèse le plus), demi-vie en rangs.
        weights = [2 ** (i / _TIME_DECAY_HALF_LIFE) for i in range(len(channels))]
        total_weight = sum(weights)
        for channel, weight in zip(channels, weights):
            attribution[channel] = attribution.get(channel, 0.0) + conversion_value * (weight / total_weight)
    else:
        raise ValueError(f"Algorithme d'attribution inconnu : {algorithm!r}")

    return attribution


def compile_weekly_scorecard(all_metrics: dict) -> WeeklyScorecard:
    """Compile les KPIs déjà calculés (par ex. via compute_kpis_node) en un
    scorecard hebdomadaire. `all_metrics` : dict plat contenant tout ou
    partie de {"cac", "ltv", "roas", "cpa", "email_roi",
    "organic_traffic_growth", "period"}  une clé absente reste `None`
    plutôt que de lever, le scorecard reflète ce qui a pu être calculé."""
    return WeeklyScorecard(
        period=all_metrics.get("period", "unknown"),
        cac=all_metrics.get("cac"),
        ltv=all_metrics.get("ltv"),
        roas=all_metrics.get("roas"),
        cpa=all_metrics.get("cpa"),
        email_roi=all_metrics.get("email_roi"),
        organic_traffic_growth=all_metrics.get("organic_traffic_growth"),
    )


__all__ = [
    "WeeklyScorecard",
    "calculate_cac",
    "calculate_ltv",
    "calculate_roas",
    "calculate_cpa",
    "calculate_email_roi",
    "calculate_organic_traffic_growth",
    "multi_touch_attribution",
    "compile_weekly_scorecard",
]
