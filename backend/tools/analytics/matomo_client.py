"""Client Matomo API  Prompt 5.6.

Authentification par token (`settings.MATOMO_API_TOKEN`, paramètre
`token_auth`), credential applicative globale  même limite structurelle
documentée dans les autres clients tiers de ce projet (pas de token par
client stocké en base). API classique Matomo (`index.php?module=API&...`,
format JSON), modules utilisés : VisitsSummary, Referrers, Actions, Goals,
Goals (e-commerce via `idGoal=ecommerceOrder`).
"""

import structlog
import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
# Les 3 méthodes du spec sans paramètre `date` explicite (get_traffic_sources,
# get_page_performance, get_ecommerce_report) l'utilisent en valeur fixe 
# repli documenté, cohérent avec la signature imposée par le spec.
_DEFAULT_DATE = "today"


class VisitsSummary(BaseModel):
    model_config = _STRICT_CONFIG

    nb_visits: int = 0
    nb_actions: int = 0
    nb_visits_converted: int = 0
    bounce_rate: float | None = None
    avg_time_on_site_seconds: float | None = None


class TrafficSources(BaseModel):
    model_config = _STRICT_CONFIG

    direct: int = 0
    search_engines: int = 0
    websites: int = 0
    social_networks: int = 0
    campaigns: int = 0


class PagePerformance(BaseModel):
    model_config = _STRICT_CONFIG

    page_url: str
    pageviews: int = 0
    avg_time_on_page_seconds: float | None = None
    bounce_rate: float | None = None
    exit_rate: float | None = None


class GoalsReport(BaseModel):
    model_config = _STRICT_CONFIG

    goals: dict[str, dict] = Field(default_factory=dict, description="goal_id (str) -> {nb_conversions, conversion_rate, revenue}")


class EcommerceReport(BaseModel):
    model_config = _STRICT_CONFIG

    revenue: float = 0.0
    nb_conversions: int = 0
    conversion_rate: float | None = None
    avg_order_value: float | None = None


_REFERRER_LABEL_TO_FIELD = {
    "Direct Entry": "direct",
    "Search Engines": "search_engines",
    "Websites": "websites",
    "Social Networks": "social_networks",
    "Campaigns": "campaigns",
}


class MatomoClient:
    def __init__(self, timeout: float = 30.0) -> None:
        if not settings.MATOMO_API_TOKEN:
            raise RuntimeError("MATOMO_API_TOKEN doit être configuré dans settings pour utiliser MatomoClient.")
        self._client = httpx.AsyncClient(base_url=settings.MATOMO_BASE_URL, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, site_id: str, period: str, date: str, **extra) -> object:
        params = {
            "module": "API",
            "method": method,
            "idSite": site_id,
            "period": period,
            "date": date,
            "format": "JSON",
            "token_auth": settings.MATOMO_API_TOKEN,
            **extra,
        }
        response = await self._client.get("/index.php", params=params)
        response.raise_for_status()
        return response.json()

    async def get_visits_summary(self, site_id: str, period: str, date: str) -> VisitsSummary:
        data = await self._call("VisitsSummary.get", site_id, period, date)
        if not isinstance(data, dict):
            data = {}
        summary = VisitsSummary(
            nb_visits=int(data.get("nb_visits", 0) or 0),
            nb_actions=int(data.get("nb_actions", 0) or 0),
            nb_visits_converted=int(data.get("nb_visits_converted", 0) or 0),
            bounce_rate=float(str(data["bounce_rate"]).rstrip("%")) / 100 if data.get("bounce_rate") else None,
            avg_time_on_site_seconds=float(data["avg_time_on_site"]) if data.get("avg_time_on_site") else None,
        )
        logger.info("matomo_client.visits_summary_fetched", site_id=site_id, period=period, nb_visits=summary.nb_visits)
        return summary

    async def get_traffic_sources(self, site_id: str, period: str) -> TrafficSources:
        data = await self._call("Referrers.getReferrerType", site_id, period, _DEFAULT_DATE)
        fields = {}
        for row in data if isinstance(data, list) else []:
            field = _REFERRER_LABEL_TO_FIELD.get(row.get("label", ""))
            if field:
                fields[field] = int(row.get("nb_visits", 0) or 0)
        sources = TrafficSources(**fields)
        logger.info("matomo_client.traffic_sources_fetched", site_id=site_id, period=period)
        return sources

    async def get_page_performance(self, site_id: str, period: str) -> list[PagePerformance]:
        data = await self._call("Actions.getPageUrls", site_id, period, _DEFAULT_DATE, flat=1)
        pages = [
            PagePerformance(
                page_url=row.get("label", ""),
                pageviews=int(row.get("nb_hits", 0) or 0),
                avg_time_on_page_seconds=float(row["avg_time_on_page"]) if row.get("avg_time_on_page") else None,
                bounce_rate=float(str(row["bounce_rate"]).rstrip("%")) / 100 if row.get("bounce_rate") else None,
                exit_rate=float(str(row["exit_rate"]).rstrip("%")) / 100 if row.get("exit_rate") else None,
            )
            for row in (data if isinstance(data, list) else [])
        ]
        logger.info("matomo_client.page_performance_fetched", site_id=site_id, period=period, page_count=len(pages))
        return pages

    async def get_goals_report(self, site_id: str, period: str) -> GoalsReport:
        data = await self._call("Goals.get", site_id, period, _DEFAULT_DATE)
        goals = data if isinstance(data, dict) else {}
        logger.info("matomo_client.goals_report_fetched", site_id=site_id, period=period, goal_count=len(goals))
        return GoalsReport(goals=goals)

    async def get_ecommerce_report(self, site_id: str, period: str) -> "EcommerceReport | None":
        try:
            data = await self._call("Goals.get", site_id, period, _DEFAULT_DATE, idGoal="ecommerceOrder")
        except httpx.HTTPError as exc:
            logger.warning("matomo_client.ecommerce_report_failed", site_id=site_id, error=str(exc))
            return None
        if not isinstance(data, dict) or not data:
            # Site sans e-commerce activé (ou aucune donnée)  Optional dans le spec.
            return None
        report = EcommerceReport(
            revenue=float(data.get("revenue", 0.0) or 0.0),
            nb_conversions=int(data.get("nb_conversions", 0) or 0),
            conversion_rate=float(str(data["conversion_rate"]).rstrip("%")) / 100 if data.get("conversion_rate") else None,
            avg_order_value=float(data["avg_order_revenue"]) if data.get("avg_order_revenue") else None,
        )
        logger.info("matomo_client.ecommerce_report_fetched", site_id=site_id, period=period, revenue=report.revenue)
        return report


__all__ = ["MatomoClient", "VisitsSummary", "TrafficSources", "PagePerformance", "GoalsReport", "EcommerceReport"]
