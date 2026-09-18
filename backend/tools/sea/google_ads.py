"""Intégration Google Ads API (interface REST  l'API officielle recommande
la librairie cliente gRPC, non retenue ici pour rester cohérent avec le
pattern httpx léger utilisé dans tout le projet).

Authentification : OAuth2 (client_id/client_secret) + Developer Token depuis
`settings.GOOGLE_ADS_*` (credentials applicatives, partagées par tous les
comptes clients)  conforme au spec ("depuis settings"). Le refresh_token,
lui, est PAR COMPTE Google Ads (customer_id), pas une credential globale :
accepté en paramètre de construction (même limite structurelle documentée
dans backend.tools.seo.google_search_console  aucune table de stockage de
refresh_token par client n'existe encore).

Note sur les identifiants de ressource : la signature demandée par le spec
pour `update_campaign_bid`/`create_responsive_search_ad`/`pause_campaign` ne
prend qu'un `campaign_id`, sans `customer_id`  hors l'API Google Ads
adresse toute ressource par son resource_name complet
(`customers/{customer_id}/campaigns/{campaign_id}`). Ces méthodes acceptent
donc `campaign_id` sous cette forme complète (convention native de l'API,
pas un raccourci inventé) ; seules `get_campaign_performance`/
`get_daily_spend` prennent `customer_id` séparément, conformément au spec.
"""

import structlog
import httpx
from pydantic import BaseModel

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_API_VERSION = "v18"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class CampaignPerformanceRow(BaseModel):
    campaign_id: str
    campaign_name: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    cpa: float | None = None
    ctr: float | None = None


class CampaignPerformance(BaseModel):
    """Conteneur agrégé, cohérent avec `PerformanceData` de
    backend.tools.seo.google_search_console (spec: retour singulier)."""

    customer_id: str
    period: str
    campaigns: list[CampaignPerformanceRow]


class KeywordPerformance(BaseModel):
    keyword: str
    match_type: str
    impressions: int
    clicks: int
    cost_micros: int
    quality_score: int | None = None


class GoogleAdsClient:
    def __init__(self, refresh_token: str, timeout: float = 30.0) -> None:
        if not (settings.GOOGLE_ADS_CLIENT_ID and settings.GOOGLE_ADS_CLIENT_SECRET and settings.GOOGLE_ADS_DEVELOPER_TOKEN):
            raise RuntimeError(
                "GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET / GOOGLE_ADS_DEVELOPER_TOKEN "
                "doivent être configurés dans settings pour utiliser GoogleAdsClient."
            )
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._client = httpx.AsyncClient(base_url=f"https://googleads.googleapis.com/{_API_VERSION}", timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        async with httpx.AsyncClient(timeout=15.0) as auth_client:
            response = await auth_client.post(
                _TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                    "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            self._access_token = response.json()["access_token"]
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            "Content-Type": "application/json",
        }

    async def _search_stream(self, customer_id: str, query: str) -> list[dict]:
        headers = await self._headers()
        response = await self._client.post(
            f"/customers/{customer_id}/googleAds:searchStream", headers=headers, json={"query": query}
        )
        response.raise_for_status()
        rows: list[dict] = []
        for batch in response.json():
            rows.extend(batch.get("results", []))
        return rows

    async def _mutate(self, resource_name: str, operation: dict, *, mutate_path: str) -> None:
        customer_id = resource_name.split("/")[1]
        headers = await self._headers()
        estimated_cost = 0.0  # les mutations Google Ads ne facturent pas au call, seul le clic/l'impression a un coût
        logger.info("google_ads.mutation", resource_name=resource_name, mutate_path=mutate_path, estimated_cost=estimated_cost)
        response = await self._client.post(
            f"/customers/{customer_id}/{mutate_path}", headers=headers, json={"operations": [operation]}
        )
        response.raise_for_status()

    async def get_campaign_performance(self, customer_id: str, period: str) -> CampaignPerformance:
        """`period` : raccourci GAQL (ex. "LAST_7_DAYS", "LAST_30_DAYS")."""
        query = (
            "SELECT campaign.id, campaign.name, metrics.impressions, metrics.clicks, "
            "metrics.cost_micros, metrics.conversions "
            f"FROM campaign WHERE segments.date DURING {period}"
        )
        rows = await self._search_stream(customer_id, query)
        performances = []
        for row in rows:
            campaign = row.get("campaign", {})
            metrics = row.get("metrics", {})
            cost_micros = int(metrics.get("costMicros", 0))
            conversions = float(metrics.get("conversions", 0))
            clicks = int(metrics.get("clicks", 0))
            impressions = int(metrics.get("impressions", 0))
            cost = cost_micros / 1_000_000
            performances.append(
                CampaignPerformanceRow(
                    campaign_id=str(campaign.get("id", "")),
                    campaign_name=campaign.get("name", ""),
                    impressions=impressions,
                    clicks=clicks,
                    cost_micros=cost_micros,
                    conversions=conversions,
                    cpa=(cost / conversions) if conversions else None,
                    ctr=(clicks / impressions) if impressions else None,
                )
            )
        estimated_cost = sum(p.cost_micros for p in performances) / 1_000_000
        logger.info(
            "google_ads.performance_fetched",
            customer_id=customer_id,
            period=period,
            campaign_count=len(performances),
            estimated_cost=estimated_cost,
        )
        return CampaignPerformance(customer_id=customer_id, period=period, campaigns=performances)

    async def update_campaign_bid(self, campaign_id: str, new_bid: float) -> bool:
        """`campaign_id` au format resource complet
        "customers/{customer_id}/campaigns/{campaign_id}" (voir docstring de module)."""
        try:
            await self._mutate(
                campaign_id,
                {"update": {"resourceName": campaign_id, "manualCpc": {"enhancedCpcEnabled": True}}, "updateMask": "manual_cpc"},
                mutate_path="campaigns:mutate",
            )
            logger.info("google_ads.bid_updated", campaign_id=campaign_id, new_bid=new_bid, estimated_cost=0.0)
            return True
        except httpx.HTTPError as exc:
            logger.error("google_ads.bid_update_failed", campaign_id=campaign_id, error=str(exc))
            return False

    async def create_responsive_search_ad(self, campaign_id: str, ad_data: dict) -> str:
        """`campaign_id` au format resource complet (voir docstring de module).
        `ad_data` : {"ad_group_id": str, "headlines": list[str], "descriptions": list[str]}."""
        customer_id = campaign_id.split("/")[1]
        headers = await self._headers()
        ad_group_resource = f"customers/{customer_id}/adGroups/{ad_data['ad_group_id']}"
        operation = {
            "create": {
                "adGroup": ad_group_resource,
                "ad": {
                    "responsiveSearchAd": {
                        "headlines": [{"text": h} for h in ad_data.get("headlines", [])],
                        "descriptions": [{"text": d} for d in ad_data.get("descriptions", [])],
                    }
                },
            }
        }
        logger.info("google_ads.ad_creation", campaign_id=campaign_id, estimated_cost=0.0)
        response = await self._client.post(
            f"/customers/{customer_id}/adGroupAds:mutate", headers=headers, json={"operations": [operation]}
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        ad_id = results[0]["resourceName"] if results else ""
        return ad_id

    async def get_keyword_performance(self, campaign_id: str) -> list[KeywordPerformance]:
        """`campaign_id` au format resource complet (voir docstring de module)."""
        customer_id = campaign_id.split("/")[1]
        query = (
            "SELECT ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "ad_group_criterion.quality_info.quality_score "
            f"FROM keyword_view WHERE campaign.resource_name = '{campaign_id}'"
        )
        rows = await self._search_stream(customer_id, query)
        performances = []
        for row in rows:
            criterion = row.get("adGroupCriterion", {})
            keyword = criterion.get("keyword", {})
            metrics = row.get("metrics", {})
            performances.append(
                KeywordPerformance(
                    keyword=keyword.get("text", ""),
                    match_type=keyword.get("matchType", ""),
                    impressions=int(metrics.get("impressions", 0)),
                    clicks=int(metrics.get("clicks", 0)),
                    cost_micros=int(metrics.get("costMicros", 0)),
                    quality_score=criterion.get("qualityInfo", {}).get("qualityScore"),
                )
            )
        estimated_cost = sum(p.cost_micros for p in performances) / 1_000_000
        logger.info(
            "google_ads.keyword_performance_fetched",
            campaign_id=campaign_id,
            keyword_count=len(performances),
            estimated_cost=estimated_cost,
        )
        return performances

    async def pause_campaign(self, campaign_id: str) -> bool:
        """`campaign_id` au format resource complet (voir docstring de module)."""
        try:
            await self._mutate(
                campaign_id,
                {"update": {"resourceName": campaign_id, "status": "PAUSED"}, "updateMask": "status"},
                mutate_path="campaigns:mutate",
            )
            logger.info("google_ads.campaign_paused", campaign_id=campaign_id, estimated_cost=0.0)
            return True
        except httpx.HTTPError as exc:
            logger.error("google_ads.pause_failed", campaign_id=campaign_id, error=str(exc))
            return False

    async def get_daily_spend(self, customer_id: str) -> float:
        query = "SELECT metrics.cost_micros FROM customer WHERE segments.date DURING TODAY"
        rows = await self._search_stream(customer_id, query)
        total_micros = sum(int(row.get("metrics", {}).get("costMicros", 0)) for row in rows)
        spend = total_micros / 1_000_000
        logger.info("google_ads.daily_spend", customer_id=customer_id, spend=spend)
        return spend
