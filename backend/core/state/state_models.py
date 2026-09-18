"""Modèles Pydantic référencés par MarketingState (marketing_state.py).

Ces modèles décrivent des structures qui circulent dans l'état LangGraph en
mémoire/checkpoints  distincts des modèles ORM de backend/db/models (une
même notion, ex. "Content", peut exister sous deux formes : un objet d'état
éphémère ici, une ligne persistée là-bas). Validation stricte partout
(`extra="forbid"`) : un champ inattendu dans l'état d'un agent est le signe
d'un bug de câblage entre nœuds, pas une entrée à absorber silencieusement.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)


class PlanItem(BaseModel):
    """Une entrée du plan hebdomadaire produit par l'Orchestrateur (plan_week_node)."""

    model_config = _STRICT_CONFIG

    agent: str
    task_type: str
    priority: int = Field(ge=1, le=5, description="1 = le plus prioritaire, 5 = le moins prioritaire.")
    deadline: datetime
    dependencies: list[str] = Field(default_factory=list, description="task_type des tâches devant précéder celle-ci.")


class Task(BaseModel):
    """Unité de travail assignée à un agent, suivie dans assigned_tasks/completed_tasks."""

    model_config = _STRICT_CONFIG

    id: str
    agent: str
    type: str
    payload: dict = Field(default_factory=dict)
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    result: Optional[dict] = None
    error: Optional[str] = None


class HITLRequest(BaseModel):
    """Demande de validation humaine (interrupt() LangGraph, hitl_checkpoint_node)."""

    model_config = _STRICT_CONFIG

    id: str
    agent: str
    action_type: str
    proposal: dict
    context: dict = Field(default_factory=dict)
    threshold_exceeded: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Keyword(BaseModel):
    """Mot-clé SEO identifié par l'Agent SEO (research_keywords_node)."""

    model_config = _STRICT_CONFIG

    term: str
    volume: Optional[int] = Field(default=None, ge=0)
    difficulty: Optional[float] = Field(default=None, ge=0, le=100)
    position: Optional[int] = Field(default=None, ge=1)
    cluster: Optional[str] = None


class CampaignConfig(BaseModel):
    """Configuration d'une campagne publicitaire produite par l'Agent SEA."""

    model_config = _STRICT_CONFIG

    name: str
    platform: Literal["google_ads", "meta_ads", "linkedin_ads", "tiktok_ads"]
    budget: float = Field(ge=0)
    targeting: dict = Field(default_factory=dict)
    creatives: list[str] = Field(default_factory=list, description="IDs ou chemins des créatifs utilisés.")


class Content(BaseModel):
    """Contenu produit par l'Agent Content  objet d'état éphémère, distinct
    du modèle ORM `backend.db.models.content.Content` (persistance)."""

    model_config = _STRICT_CONFIG

    id: str
    type: Literal["article", "post", "email", "landing_page", "visual"]
    platform: Literal["linkedin", "meta", "tiktok", "email", "web"]
    title: Optional[str] = None
    body: str
    status: Literal["draft", "review", "published", "archived"] = "draft"
    metadata: dict = Field(default_factory=dict)


class VisualAsset(BaseModel):
    """Visuel produit par l'Agent Créatif (pipeline ComfyUI)."""

    model_config = _STRICT_CONFIG

    id: str
    type: Literal["image", "video", "carousel"]
    format: Literal["png", "jpg", "gif", "mp4", "webp"]
    file_path: str
    dimensions: str = Field(description='Dimensions en pixels, ex. "1080x1080".')
    style_tags: list[str] = Field(default_factory=list)


class AgentError(BaseModel):
    """Erreur remontée par un agent  Annotated[list[AgentError], operator.add]
    dans MarketingState : chaque agent ajoute la sienne, jamais de remplacement."""

    model_config = _STRICT_CONFIG

    agent: str
    error_type: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    recoverable: bool = True


class Alert(BaseModel):
    """Alerte destinée au monitoring/à l'interface (budget dépassé, anomalie...)."""

    model_config = _STRICT_CONFIG

    level: Literal["info", "warning", "critical"]
    source: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action_required: bool = False
