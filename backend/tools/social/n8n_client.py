"""Client n8n pour l'automatisation sociale  Prompt 5.4.

Deux surfaces distinctes de l'API n8n, utilisées pour deux usages différents
(choix documenté, pas une confusion) :
- Déclenchement (`trigger_workflow`) : via l'URL webhook du workflow
  (`{base_url}/webhook/{workflow_id}`), la façon standard de déclencher un
  workflow n8n depuis un service externe  pas d'authentification par défaut
  (dépend de la configuration du nœud Webhook côté n8n).
- Introspection (`get_workflow_status`/`get_available_workflows`) : via la
  vraie API REST n8n (`{base_url}/api/v1/...`), qui nécessite le header
  `X-N8N-API-KEY` (`settings.N8N_API_KEY`).
"""

import structlog
import httpx
from pydantic import BaseModel, ConfigDict

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# Identifiants des workflows n8n disponibles (spec Prompt 5.4). Ce sont des
# noms de webhook n8n, pas des UUID  convention à respecter côté n8n lors de
# la création des workflows correspondants.
WORKFLOW_LINKEDIN_POST = "LINKEDIN_POST"
WORKFLOW_META_POST = "META_POST"
WORKFLOW_TIKTOK_POST = "TIKTOK_POST"
WORKFLOW_SOCIAL_METRICS_COLLECT = "SOCIAL_METRICS_COLLECT"
WORKFLOW_SOCIAL_MENTIONS_MONITOR = "SOCIAL_MENTIONS_MONITOR"

AVAILABLE_WORKFLOWS = (
    WORKFLOW_LINKEDIN_POST,
    WORKFLOW_META_POST,
    WORKFLOW_TIKTOK_POST,
    WORKFLOW_SOCIAL_METRICS_COLLECT,
    WORKFLOW_SOCIAL_MENTIONS_MONITOR,
)


class WorkflowExecution(BaseModel):
    model_config = _STRICT_CONFIG

    execution_id: str
    workflow_id: str
    status: str


class ExecutionStatus(BaseModel):
    model_config = _STRICT_CONFIG

    execution_id: str
    status: str
    finished: bool
    data: dict | None = None


class Workflow(BaseModel):
    model_config = _STRICT_CONFIG

    id: str
    name: str
    active: bool = True


class N8nClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = (base_url or settings.N8N_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _api_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if settings.N8N_API_KEY:
            headers["X-N8N-API-KEY"] = settings.N8N_API_KEY
        return headers

    async def trigger_workflow(self, workflow_id: str, payload: dict) -> WorkflowExecution:
        response = await self._client.post(f"/webhook/{workflow_id}", json=payload)
        response.raise_for_status()
        body = response.json() if response.content else {}
        execution_id = str(body.get("execution_id") or body.get("executionId") or "")
        status = body.get("status", "triggered")
        logger.info("n8n_client.workflow_triggered", workflow_id=workflow_id, execution_id=execution_id)
        return WorkflowExecution(execution_id=execution_id, workflow_id=workflow_id, status=status)

    async def get_workflow_status(self, execution_id: str) -> ExecutionStatus:
        response = await self._client.get(f"/api/v1/executions/{execution_id}", headers=self._api_headers())
        response.raise_for_status()
        body = response.json()
        return ExecutionStatus(
            execution_id=execution_id,
            status=body.get("status", "unknown"),
            finished=bool(body.get("finished", False)),
            data=body.get("data"),
        )

    async def get_available_workflows(self) -> list[Workflow]:
        response = await self._client.get("/api/v1/workflows", headers=self._api_headers())
        response.raise_for_status()
        items = response.json().get("data", [])
        return [Workflow(id=str(item["id"]), name=item.get("name", ""), active=item.get("active", True)) for item in items]


__all__ = [
    "N8nClient",
    "WorkflowExecution",
    "ExecutionStatus",
    "Workflow",
    "WORKFLOW_LINKEDIN_POST",
    "WORKFLOW_META_POST",
    "WORKFLOW_TIKTOK_POST",
    "WORKFLOW_SOCIAL_METRICS_COLLECT",
    "WORKFLOW_SOCIAL_MENTIONS_MONITOR",
    "AVAILABLE_WORKFLOWS",
]
