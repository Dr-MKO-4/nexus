"""Intégration Google Search Console API (Search Analytics, webmasters/v3).

Authentification OAuth2 PAR CLIENT (chaque client NEXUS AI autorise l'accès à
SA propriété GSC)  distincte des credentials Google Ads globales de
`settings.GOOGLE_ADS_*`. Aucune table de stockage des tokens OAuth par
client n'existe encore (backend/db/models/clients.py n'a pas ce champ) :
`GoogleSearchConsoleClient` accepte un `access_token` directement en
paramètre de construction plutôt que de le lire depuis settings  le point
de récupération/rafraîchissement du token par client reste à câbler (TODO
explicite, pas une omission silencieuse).
"""

from urllib.parse import quote

import httpx
import structlog
from pydantic import BaseModel

from backend.core.memory.redis_client import RedisClient, get_redis_client

logger = structlog.get_logger(__name__)

_API_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6h, cache des données de performance (spec)
_PAGE_SIZE = 10  # pagination imposée par l'API depuis septembre 2025 (spec)


class PerformanceRow(BaseModel):
    page: str
    query: str | None = None
    clicks: int
    impressions: int
    ctr: float
    position: float


class PerformanceData(BaseModel):
    site_url: str
    period: str
    rows: list[PerformanceRow]


class CoverageData(BaseModel):
    site_url: str
    indexed_count: int
    excluded_count: int
    error_count: int


class CrawlError(BaseModel):
    url: str
    category: str
    last_detected: str


class GoogleSearchConsoleClient:
    def __init__(self, access_token: str, redis_client: RedisClient | None = None, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=_API_BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )
        self._redis = redis_client or get_redis_client()

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _cache_key(method: str, site_url: str, period: str) -> str:
        return f"gsc:{method}:{site_url}:{period}"

    @staticmethod
    def _site_path(site_url: str) -> str:
        return quote(site_url, safe="")

    async def _paginated_query(self, site_url: str, start_date: str, end_date: str) -> list[dict]:
        rows: list[dict] = []
        start_row = 0
        while True:
            response = await self._client.post(
                f"/sites/{self._site_path(site_url)}/searchAnalytics/query",
                json={
                    "startDate": start_date,
                    "endDate": end_date,
                    "dimensions": ["page", "query"],
                    "rowLimit": _PAGE_SIZE,
                    "startRow": start_row,
                },
            )
            response.raise_for_status()
            page = response.json().get("rows", [])
            rows.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            start_row += _PAGE_SIZE
        return rows

    async def get_performance_report(self, site_url: str, period: str) -> PerformanceData:
        """Impressions/clics/positions/CTR par page et mot-clé, avec
        pagination automatique (10 résultats/page) et cache Redis 6h."""
        cache_key = self._cache_key("performance", site_url, period)

        async def _fetch() -> dict:
            start_date, end_date = _parse_period(period)
            raw_rows = await self._paginated_query(site_url, start_date, end_date)
            rows = [
                {
                    "page": r["keys"][0],
                    "query": r["keys"][1] if len(r["keys"]) > 1 else None,
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                    "ctr": r.get("ctr", 0.0),
                    "position": r.get("position", 0.0),
                }
                for r in raw_rows
            ]
            logger.info("gsc.performance_fetched", site_url=site_url, period=period, row_count=len(rows))
            return {"site_url": site_url, "period": period, "rows": rows}

        cached = await self._redis.get_or_set(cache_key, _fetch, ttl=_CACHE_TTL_SECONDS)
        return PerformanceData.model_validate(cached)

    async def get_index_coverage(self, site_url: str) -> CoverageData:
        """L'API Search Analytics ne donne pas la couverture d'indexation
        directement (c'est l'Index Coverage report, exposé côté UI GSC sans
        endpoint Search Analytics dédié)  approximé ici via le nombre de
        pages distinctes présentes dans les 28 derniers jours de
        performance comme proxy de "indexé et servant du trafic"."""
        performance = await self.get_performance_report(site_url, "28d")
        indexed_pages = {row.page for row in performance.rows}
        return CoverageData(
            site_url=site_url,
            indexed_count=len(indexed_pages),
            excluded_count=0,
            error_count=0,
        )

    async def get_crawl_errors(self, site_url: str) -> list[CrawlError]:
        """L'API Search Analytics ne remonte pas les erreurs de crawl (URL
        Inspection API le permettrait, par URL individuelle uniquement, pas
        en liste)  liste vide en l'absence d'un inventaire d'URLs à
        inspecter une par une. Point d'extension futur, pas un TODO
        silencieux : voir docstring de get_index_coverage pour la même
        limite structurelle de l'API GSC."""
        logger.debug("gsc.crawl_errors_not_available_via_search_analytics_api", site_url=site_url)
        return []


def _parse_period(period: str) -> tuple[str, str]:
    """Convertit un raccourci de période ("7d", "28d", "90d") en
    (start_date, end_date) ISO 8601, end_date = aujourd'hui."""
    from datetime import date, timedelta

    if not period.endswith("d"):
        raise ValueError(f"Format de période non supporté : {period!r} (attendu ex. '7d', '28d', '90d')")
    days = int(period[:-1])
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()
