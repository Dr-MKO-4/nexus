"""Intégration Meta Marketing API (Graph API).

Authentification : `settings.META_APP_ID`/`META_APP_SECRET` identifient
l'application NEXUS AI elle-même (credentials applicatives) ; l'accès à un
compte publicitaire précis nécessite en plus un access_token utilisateur/
système PAR COMPTE  accepté en paramètre de construction, même limite
structurelle documentée dans backend.tools.sea.google_ads (aucune table de
stockage de token par client n'existe encore).
"""

import structlog
import httpx
from pydantic import BaseModel

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_API_VERSION = "v21.0"
_GRAPH_API_BASE = f"https://graph.facebook.com/{_API_VERSION}"


class InsightsData(BaseModel):
    account_id: str
    period: str
    impressions: int
    clicks: int
    spend: float
    ctr: float | None = None
    cpc: float | None = None


class AudienceData(BaseModel):
    account_id: str
    estimated_audience_size: int | None = None
    targeting_summary: dict


class MetaAdsClient:
    def __init__(self, access_token: str, timeout: float = 30.0) -> None:
        if not (settings.META_APP_ID and settings.META_APP_SECRET):
            raise RuntimeError("META_APP_ID / META_APP_SECRET doivent être configurés dans settings pour utiliser MetaAdsClient.")
        self._access_token = access_token
        self._client = httpx.AsyncClient(base_url=_GRAPH_API_BASE, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _params(self, **extra: object) -> dict:
        return {"access_token": self._access_token, **extra}

    async def get_ad_account_insights(self, account_id: str, period: str) -> InsightsData:
        """`period` : raccourci Meta Insights ("today", "last_7d", "last_30d"...)."""
        response = await self._client.get(
            f"/act_{account_id}/insights",
            params=self._params(date_preset=period, fields="impressions,clicks,spend,ctr,cpc"),
        )
        response.raise_for_status()
        rows = response.json().get("data", [])
        row = rows[0] if rows else {}

        logger.info("meta_ads.insights_fetched", account_id=account_id, period=period)
        return InsightsData(
            account_id=account_id,
            period=period,
            impressions=int(row.get("impressions", 0)),
            clicks=int(row.get("clicks", 0)),
            spend=float(row.get("spend", 0.0)),
            ctr=float(row["ctr"]) if row.get("ctr") is not None else None,
            cpc=float(row["cpc"]) if row.get("cpc") is not None else None,
        )

    async def create_campaign(self, account_id: str, campaign_data: dict) -> str:
        """`campaign_data` : {"name": str, "objective": str, "status": str = "PAUSED", ...}.
        Statut par défaut PAUSED : une campagne créée par un agent ne doit
        jamais partir active sans validation humaine explicite."""
        payload = self._params(
            name=campaign_data["name"],
            objective=campaign_data.get("objective", "OUTCOME_TRAFFIC"),
            status=campaign_data.get("status", "PAUSED"),
            special_ad_categories=campaign_data.get("special_ad_categories", []),
        )
        response = await self._client.post(f"/act_{account_id}/campaigns", data=payload)
        response.raise_for_status()
        campaign_id = response.json()["id"]
        logger.info("meta_ads.campaign_created", account_id=account_id, campaign_id=campaign_id, estimated_cost=0.0)
        return campaign_id

    async def update_ad_set_budget(self, adset_id: str, daily_budget: float) -> bool:
        try:
            response = await self._client.post(
                f"/{adset_id}", data=self._params(daily_budget=int(daily_budget * 100))  # Meta attend des centimes
            )
            response.raise_for_status()
            logger.info("meta_ads.budget_updated", adset_id=adset_id, daily_budget=daily_budget, estimated_cost=0.0)
            return True
        except httpx.HTTPError as exc:
            logger.error("meta_ads.budget_update_failed", adset_id=adset_id, error=str(exc))
            return False

    async def generate_ad_creative(self, campaign_id: str, creative_data: dict) -> str:
        """`creative_data` : {"account_id": str, "page_id": str, "message": str,
        "link": str, "image_hash": str | None}. `account_id` est requis (une
        création de créatif Meta cible toujours /act_{account_id}/adcreatives) :
        absent, on lève une erreur explicite plutôt que de construire une URL
        invalide (/act_None/...)."""
        if not creative_data.get("account_id"):
            raise ValueError("creative_data['account_id'] est requis pour generate_ad_creative.")
        object_story_spec = {
            "page_id": creative_data["page_id"],
            "link_data": {
                "message": creative_data.get("message", ""),
                "link": creative_data.get("link", ""),
                **({"image_hash": creative_data["image_hash"]} if creative_data.get("image_hash") else {}),
            },
        }
        account_id = creative_data["account_id"]
        response = await self._client.post(
            f"/act_{account_id}/adcreatives",
            data=self._params(
                name=f"creative-{campaign_id}",
                object_story_spec=str(object_story_spec).replace("'", '"'),
            ),
        )
        response.raise_for_status()
        creative_id = response.json()["id"]
        logger.info("meta_ads.creative_generated", campaign_id=campaign_id, creative_id=creative_id, estimated_cost=0.0)
        return creative_id

    async def get_audience_insights(self, account_id: str, targeting: dict) -> AudienceData:
        response = await self._client.get(
            f"/act_{account_id}/reachestimate",
            params=self._params(targeting_spec=str(targeting).replace("'", '"')),
        )
        response.raise_for_status()
        body = response.json().get("data", {})

        logger.info("meta_ads.audience_insights_fetched", account_id=account_id)
        estimated_audience_size = body.get("users") if body.get("estimate_ready") else None
        return AudienceData(
            account_id=account_id,
            estimated_audience_size=estimated_audience_size,
            targeting_summary=targeting,
        )
