"""MarketingState : l'unique objet d'état qui circule dans tout le graphe
LangGraph d'orchestration (racine + subgraphs acquisition/engagement/mesure)
pendant l'exécution d'une campagne  voir backend/agents/orchestrator/graph.py
et backend/core/graph/main_graph.py (Prompts 4.2/4.3, pas encore écrits).

Champs `Annotated[..., operator.add]` : écrits par plusieurs agents en
parallèle lors d'un fanout (Send API LangGraph, clusters Acquisition/
Engagement)  sans ce reducer, deux écritures concurrentes sur le même champ
dans le même step font lever `InvalidUpdateError` à LangGraph plutôt que de
fusionner (vérifié empiriquement sur un projet voisin utilisant le même
pattern d'état). Tous les autres champs sont écrits par un seul nœud à la
fois (l'Orchestrateur, ou un agent dédié à ce champ) : la sémantique
"dernière écriture gagne" par défaut de LangGraph leur convient telle quelle.
"""

import operator
from datetime import datetime
from typing import Annotated, Literal, Optional, TypedDict

from backend.core.state.state_models import (
    Alert,
    AgentError,
    CampaignConfig,
    Content,
    HITLRequest,
    Keyword,
    PlanItem,
    Task,
    VisualAsset,
)


class MarketingState(TypedDict):
    # ── Contexte business ────────────────────────────────────────────────
    objective: str
    client_id: str
    campaign_id: Optional[str]
    budget_total: float
    budget_consumed: float
    channel_allocations: dict[str, float]
    period_start: datetime
    period_end: datetime

    # ── Planification orchestrateur ──────────────────────────────────────
    weekly_plan: list[PlanItem]
    assigned_tasks: dict[str, list[Task]]
    completed_tasks: list[Task]
    pending_validations: list[HITLRequest]

    # ── Résultats agents ──────────────────────────────────────────────────
    seo_keywords: list[Keyword]
    seo_audit_results: Optional[dict]
    sea_campaigns: list[CampaignConfig]
    generated_contents: Annotated[list[Content], operator.add]
    published_contents: list[str]
    email_sequences_triggered: list[str]
    analytics_data: Optional[dict]
    performance_summary: Optional[dict]
    visual_assets: list[VisualAsset]

    # ── Contrôle de flux ──────────────────────────────────────────────────
    active_agent: Optional[str]
    completed_agents: Annotated[list[str], operator.add]
    errors: Annotated[list[AgentError], operator.add]
    alerts: Annotated[list[Alert], operator.add]
    iterations: int
    max_iterations: int
    hitl_required: bool
    hitl_response: Optional[dict]
    execution_mode: Literal["planning", "execution", "optimization", "crisis"]

    # ── Metadata ──────────────────────────────────────────────────────────
    trace_id: str
    session_id: str
    created_at: datetime
    last_updated_at: datetime


DEFAULT_MAX_ITERATIONS = 5
