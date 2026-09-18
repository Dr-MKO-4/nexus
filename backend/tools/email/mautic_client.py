"""Client Mautic API complet  Prompt 5.5.

Authentification OAuth2 (`client_credentials`, `settings.MAUTIC_CLIENT_ID`/
`MAUTIC_CLIENT_SECRET`)  credentials applicatives globales, cohérent avec le
pattern déjà utilisé pour Google Ads (`backend.tools.sea.google_ads`).

Endpoints REST Mautic (API v2, stable depuis Mautic 2.x/3.x/4.x) :
contacts (`/api/contacts/*`), segments (`/api/segments/*`, appelés "lists"
en interne côté Mautic mais exposés sous `/api/segments` depuis Mautic 3),
campagnes (`/api/campaigns/*`), emails (`/api/emails/*`). Mautic n'expose pas
d'endpoint REST dédié "stats de campagne" stable entre versions  voir
`get_campaign_stats` pour le choix documenté.
"""

import structlog
import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
_TOKEN_PATH = "/oauth/v2/token"


class EmailInteraction(BaseModel):
    model_config = _STRICT_CONFIG

    email_id: str | None = None
    event_type: str
    timestamp: str


class Contact(BaseModel):
    model_config = _STRICT_CONFIG

    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    segment_tags: list[str] = Field(default_factory=list)
    behavior_data: dict = Field(default_factory=dict)
    lead_score: int = 0
    last_interaction_at: str | None = None
    opted_out: bool = False


class ExecutionResult(BaseModel):
    model_config = _STRICT_CONFIG

    campaign_id: str
    contacts_triggered: list[str]
    status: str


class CampaignStats(BaseModel):
    model_config = _STRICT_CONFIG

    campaign_id: str
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    bounced: int = 0
    unsubscribed: int = 0
    open_rate: float | None = None
    click_rate: float | None = None


class MauticClient:
    def __init__(self, timeout: float = 30.0) -> None:
        if not (settings.MAUTIC_CLIENT_ID and settings.MAUTIC_CLIENT_SECRET):
            raise RuntimeError(
                "MAUTIC_CLIENT_ID / MAUTIC_CLIENT_SECRET doivent être configurés dans settings pour utiliser MauticClient."
            )
        self._access_token: str | None = None
        self._client = httpx.AsyncClient(base_url=settings.MAUTIC_BASE_URL, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _ensure_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        async with httpx.AsyncClient(base_url=settings.MAUTIC_BASE_URL, timeout=15.0) as auth_client:
            response = await auth_client.post(
                _TOKEN_PATH,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.MAUTIC_CLIENT_ID,
                    "client_secret": settings.MAUTIC_CLIENT_SECRET,
                },
            )
            response.raise_for_status()
            self._access_token = response.json()["access_token"]
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @staticmethod
    def _contact_from_payload(payload: dict) -> Contact:
        fields = payload.get("fields", {}).get("core", {})
        return Contact(
            id=str(payload.get("id", "")),
            email=fields.get("email", {}).get("value", "") if isinstance(fields.get("email"), dict) else payload.get("email", ""),
            first_name=fields.get("firstname", {}).get("value") if isinstance(fields.get("firstname"), dict) else None,
            last_name=fields.get("lastname", {}).get("value") if isinstance(fields.get("lastname"), dict) else None,
            segment_tags=payload.get("tags", []) or [],
            behavior_data=payload.get("behavior_data", {}) or {},
            lead_score=int(payload.get("points", 0) or 0),
            last_interaction_at=payload.get("lastActive"),
            opted_out=bool(payload.get("doNotContact")),
        )

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    async def create_contact(self, contact_data: dict) -> str:
        headers = await self._headers()
        response = await self._client.post("/api/contacts/new", headers=headers, json=contact_data)
        response.raise_for_status()
        contact_id = str(response.json()["contact"]["id"])
        logger.info("mautic_client.contact_created", contact_id=contact_id)
        return contact_id

    async def update_contact(self, contact_id: str, data: dict) -> bool:
        headers = await self._headers()
        try:
            response = await self._client.patch(f"/api/contacts/{contact_id}/edit", headers=headers, json=data)
            response.raise_for_status()
            logger.info("mautic_client.contact_updated", contact_id=contact_id)
            return True
        except httpx.HTTPError as exc:
            logger.error("mautic_client.contact_update_failed", contact_id=contact_id, error=str(exc))
            return False

    async def add_contact_to_segment(self, contact_id: str, segment_id: str) -> bool:
        headers = await self._headers()
        try:
            response = await self._client.post(
                f"/api/segments/{segment_id}/contact/{contact_id}/add", headers=headers
            )
            response.raise_for_status()
            logger.info("mautic_client.contact_added_to_segment", contact_id=contact_id, segment_id=segment_id)
            return True
        except httpx.HTTPError as exc:
            logger.error("mautic_client.add_to_segment_failed", contact_id=contact_id, segment_id=segment_id, error=str(exc))
            return False

    async def get_contact_history(self, contact_id: str) -> list[EmailInteraction]:
        """Historique d'interactions email  endpoint `/api/contacts/{id}/events`,
        filtré sur les événements liés aux emails (`eventType=email`) : Mautic
        expose un flux d'événements générique (page views, form submits,
        emails...), pas un historique email dédié."""
        headers = await self._headers()
        response = await self._client.get(
            f"/api/contacts/{contact_id}/events", headers=headers, params={"filters[search]": "email"}
        )
        response.raise_for_status()
        events = response.json().get("events", [])
        interactions = [
            EmailInteraction(
                email_id=str(e.get("eventId")) if e.get("eventId") is not None else None,
                event_type=e.get("eventType", e.get("event", "unknown")),
                timestamp=e.get("timestamp", ""),
            )
            for e in events
        ]
        logger.info("mautic_client.contact_history_fetched", contact_id=contact_id, interaction_count=len(interactions))
        return interactions

    # ------------------------------------------------------------------
    # Segments
    # ------------------------------------------------------------------

    async def create_segment(self, name: str, filters: dict) -> str:
        headers = await self._headers()
        response = await self._client.post(
            "/api/segments/new", headers=headers, json={"name": name, "filters": filters, "isPublished": True}
        )
        response.raise_for_status()
        segment_id = str(response.json()["list"]["id"])
        logger.info("mautic_client.segment_created", segment_id=segment_id, name=name)
        return segment_id

    async def get_segment_contacts(self, segment_id: str) -> list[Contact]:
        headers = await self._headers()
        response = await self._client.get(f"/api/segments/{segment_id}/contacts", headers=headers)
        response.raise_for_status()
        contacts_payload = response.json().get("contacts", {})
        contacts = [self._contact_from_payload(c) for c in contacts_payload.values()]
        logger.info("mautic_client.segment_contacts_fetched", segment_id=segment_id, contact_count=len(contacts))
        return contacts

    # ------------------------------------------------------------------
    # Campagnes
    # ------------------------------------------------------------------

    async def create_email_campaign(self, campaign_data: dict) -> str:
        headers = await self._headers()
        response = await self._client.post("/api/campaigns/new", headers=headers, json=campaign_data)
        response.raise_for_status()
        campaign_id = str(response.json()["campaign"]["id"])
        logger.info("mautic_client.campaign_created", campaign_id=campaign_id)
        return campaign_id

    async def trigger_campaign(self, campaign_id: str, contact_ids: list[str]) -> ExecutionResult:
        """Mautic n'a pas d'endpoint "trigger en masse" pour une campagne
        pilotée par événements  chaque contact est ajouté individuellement
        (`/api/campaigns/{id}/contact/{contactId}/add`), ce qui l'inscrit
        dans le déclencheur de la campagne."""
        headers = await self._headers()
        triggered: list[str] = []
        for contact_id in contact_ids:
            try:
                response = await self._client.post(
                    f"/api/campaigns/{campaign_id}/contact/{contact_id}/add", headers=headers
                )
                response.raise_for_status()
                triggered.append(contact_id)
            except httpx.HTTPError as exc:
                logger.warning("mautic_client.campaign_trigger_contact_failed", campaign_id=campaign_id, contact_id=contact_id, error=str(exc))

        status = "success" if len(triggered) == len(contact_ids) else ("partial" if triggered else "failed")
        logger.info("mautic_client.campaign_triggered", campaign_id=campaign_id, triggered_count=len(triggered), status=status)
        return ExecutionResult(campaign_id=campaign_id, contacts_triggered=triggered, status=status)

    async def get_campaign_stats(self, campaign_id: str) -> CampaignStats:
        """Mautic ne garantit pas un endpoint REST stable de statistiques
        agrégées de campagne entre versions (souvent recalculées côté UI à
        partir de `email_stats`)  repli sur `GET /api/campaigns/{id}` et
        extraction best-effort des compteurs présents dans la réponse,
        0 par défaut si absents plutôt qu'une erreur."""
        headers = await self._headers()
        response = await self._client.get(f"/api/campaigns/{campaign_id}", headers=headers)
        response.raise_for_status()
        stats = response.json().get("campaign", {}).get("stats", {})

        sent = int(stats.get("sent", 0) or 0)
        opened = int(stats.get("opened", 0) or 0)
        clicked = int(stats.get("clicked", 0) or 0)
        return CampaignStats(
            campaign_id=campaign_id,
            sent=sent,
            opened=opened,
            clicked=clicked,
            bounced=int(stats.get("bounced", 0) or 0),
            unsubscribed=int(stats.get("unsubscribed", 0) or 0),
            open_rate=(opened / sent) if sent else None,
            click_rate=(clicked / sent) if sent else None,
        )

    # ------------------------------------------------------------------
    # Emails
    # ------------------------------------------------------------------

    async def create_email_template(self, template_data: dict) -> str:
        headers = await self._headers()
        response = await self._client.post("/api/emails/new", headers=headers, json=template_data)
        response.raise_for_status()
        email_id = str(response.json()["email"]["id"])
        logger.info("mautic_client.email_template_created", email_id=email_id)
        return email_id

    async def send_email(self, email_id: str, contact_id: str) -> bool:
        headers = await self._headers()
        try:
            response = await self._client.post(f"/api/emails/{email_id}/contact/{contact_id}/send", headers=headers)
            response.raise_for_status()
            logger.info("mautic_client.email_sent", email_id=email_id, contact_id=contact_id)
            return True
        except httpx.HTTPError as exc:
            logger.error("mautic_client.email_send_failed", email_id=email_id, contact_id=contact_id, error=str(exc))
            return False


__all__ = ["MauticClient", "Contact", "EmailInteraction", "ExecutionResult", "CampaignStats"]
