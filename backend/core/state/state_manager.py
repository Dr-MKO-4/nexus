"""Gestionnaire d'état : création, validation, résumé pour le monitoring,
fusion post-fanout et (dé)sérialisation de MarketingState.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

from backend.core.state.marketing_state import DEFAULT_MAX_ITERATIONS, MarketingState
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

logger = structlog.get_logger(__name__)

# Champs Annotated[..., operator.add] de MarketingState (voir marketing_state.py) :
# seule source de vérité sur "quels champs se concatènent"  dupliquée ici
# volontairement en constante explicite plutôt qu'introspectée dynamiquement
# depuis le TypedDict (TypedDict n'expose pas ses reducers Annotated à
# l'exécution de façon simple et fiable).
CONCAT_FIELDS: tuple[str, ...] = ("generated_contents", "completed_agents", "errors", "alerts")


class StateValidationError(BaseModel):
    """Distinct de pydantic.ValidationError (que nous ne construisons pas à
    la main) : une erreur de cohérence MÉTIER de l'état, pas une erreur de
    parsing d'un champ Pydantic individuel."""

    model_config = _STRICT_CONFIG

    field: str
    message: str


class BudgetStatus(BaseModel):
    model_config = _STRICT_CONFIG

    total: float
    consumed: float
    remaining: float
    percentage_used: float
    is_exceeded: bool
    is_near_limit: bool = Field(description="≥ 90% du budget consommé, sans être dépassé.")


def create_initial_state(
    objective: str,
    client_id: str,
    budget: float,
    *,
    campaign_id: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    channel_allocations: dict[str, float] | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    trace_id: str | None = None,
    session_id: str | None = None,
) -> MarketingState:
    """Construit un MarketingState initial, prêt à être passé à
    `main_graph.run()` (Prompt 4.3, pas encore écrit)."""
    now = datetime.now(timezone.utc)
    return MarketingState(
        objective=objective,
        client_id=client_id,
        campaign_id=campaign_id,
        budget_total=budget,
        budget_consumed=0.0,
        channel_allocations=channel_allocations or {},
        period_start=period_start or now,
        period_end=period_end or now,
        weekly_plan=[],
        assigned_tasks={},
        completed_tasks=[],
        pending_validations=[],
        seo_keywords=[],
        seo_audit_results=None,
        sea_campaigns=[],
        generated_contents=[],
        published_contents=[],
        email_sequences_triggered=[],
        analytics_data=None,
        performance_summary=None,
        visual_assets=[],
        active_agent=None,
        completed_agents=[],
        errors=[],
        alerts=[],
        iterations=0,
        max_iterations=max_iterations,
        hitl_required=False,
        hitl_response=None,
        execution_mode="planning",
        trace_id=trace_id or str(uuid.uuid4()),
        session_id=session_id or str(uuid.uuid4()),
        created_at=now,
        last_updated_at=now,
    )


def validate_state(state: MarketingState) -> list[StateValidationError]:
    """Vérifie la cohérence MÉTIER de l'état (pas la conformité de type,
    déjà garantie par les modèles Pydantic imbriqués) : budget, itérations,
    présence des champs obligatoires, cohérence des dates."""
    errors: list[StateValidationError] = []

    for field in ("objective", "client_id", "trace_id", "session_id"):
        if not state.get(field):
            errors.append(StateValidationError(field=field, message="Champ obligatoire manquant ou vide."))

    if state.get("budget_total", 0) < 0:
        errors.append(StateValidationError(field="budget_total", message="budget_total ne peut pas être négatif."))

    if state.get("budget_consumed", 0) > state.get("budget_total", 0):
        errors.append(
            StateValidationError(
                field="budget_consumed",
                message=f"budget_consumed ({state.get('budget_consumed')}) dépasse budget_total ({state.get('budget_total')}).",
            )
        )

    if state.get("iterations", 0) > state.get("max_iterations", 0):
        errors.append(
            StateValidationError(
                field="iterations",
                message=f"iterations ({state.get('iterations')}) dépasse max_iterations ({state.get('max_iterations')}).",
            )
        )

    period_start, period_end = state.get("period_start"), state.get("period_end")
    if period_start and period_end and period_start > period_end:
        errors.append(StateValidationError(field="period_end", message="period_end est antérieure à period_start."))

    return errors


def get_state_summary(state: MarketingState) -> dict[str, Any]:
    """Résumé compact pour les logs/le monitoring  jamais l'état complet
    (trop volumineux, contenu potentiellement sensible dans generated_contents)."""
    return {
        "trace_id": state.get("trace_id"),
        "session_id": state.get("session_id"),
        "client_id": state.get("client_id"),
        "campaign_id": state.get("campaign_id"),
        "execution_mode": state.get("execution_mode"),
        "active_agent": state.get("active_agent"),
        "iterations": f"{state.get('iterations', 0)}/{state.get('max_iterations', 0)}",
        "budget": f"{state.get('budget_consumed', 0):.2f}/{state.get('budget_total', 0):.2f}",
        "completed_agents": list(state.get("completed_agents") or []),
        "pending_validations": len(state.get("pending_validations") or []),
        "hitl_required": state.get("hitl_required", False),
        "counts": {
            "seo_keywords": len(state.get("seo_keywords") or []),
            "sea_campaigns": len(state.get("sea_campaigns") or []),
            "generated_contents": len(state.get("generated_contents") or []),
            "published_contents": len(state.get("published_contents") or []),
            "visual_assets": len(state.get("visual_assets") or []),
            "errors": len(state.get("errors") or []),
            "alerts": len(state.get("alerts") or []),
        },
        "last_updated_at": state.get("last_updated_at"),
    }


def merge_parallel_results(states: list[MarketingState]) -> MarketingState:
    """Fusionne plusieurs MarketingState partiels obtenus après un fanout
    parallèle, en dehors de l'exécution normale du graphe (ex. agrégation
    manuelle de résultats de sous-graphes). Reproduit la sémantique des
    reducers LangGraph : les champs de CONCAT_FIELDS sont concaténés dans
    l'ordre des `states`, tous les autres suivent la sémantique "dernière
    valeur non vide gagne" (LastValue)  cohérent avec le comportement par
    défaut de LangGraph pour un champ sans Annotated.

    Note : LangGraph applique normalement ces reducers lui-même à chaque
    step du graphe ; cette fonction sert aux cas où la fusion doit être
    faite explicitement en dehors d'une exécution de graphe (ex. tests,
    agrégation de checkpoints récupérés séparément).
    """
    if not states:
        raise ValueError("merge_parallel_results nécessite au moins un état.")

    merged: dict[str, Any] = dict(states[0])
    for state in states[1:]:
        for key, value in state.items():
            if key in CONCAT_FIELDS:
                merged[key] = list(merged.get(key) or []) + list(value or [])
            elif value not in (None, [], {}, ""):
                merged[key] = value

    merged["last_updated_at"] = datetime.now(timezone.utc)
    return MarketingState(**merged)  # type: ignore[typeddict-item]


def check_budget_status(state: MarketingState) -> BudgetStatus:
    total = state.get("budget_total", 0.0)
    consumed = state.get("budget_consumed", 0.0)
    percentage = (consumed / total * 100) if total > 0 else 0.0
    return BudgetStatus(
        total=total,
        consumed=consumed,
        remaining=max(0.0, total - consumed),
        percentage_used=percentage,
        is_exceeded=consumed > total,
        is_near_limit=percentage >= 90 and consumed <= total,
    )


# ----------------------------------------------------------------------------
# (Dé)sérialisation
#
# Note : PostgresSaver de LangGraph a son propre mécanisme de sérialisation
# (langgraph.checkpoint.serde), qui gère déjà nativement les modèles Pydantic
# et les datetime présents dans l'état  ces fonctions ne sont PAS requises
# pour que le checkpointing LangGraph fonctionne. Elles servent aux usages
# hors LangGraph : logs structurés, réponses API, exports de debug, tests.
# ----------------------------------------------------------------------------

_LIST_MODEL_FIELDS: dict[str, type[BaseModel]] = {
    "weekly_plan": PlanItem,
    "completed_tasks": Task,
    "pending_validations": HITLRequest,
    "seo_keywords": Keyword,
    "sea_campaigns": CampaignConfig,
    "generated_contents": Content,
    "visual_assets": VisualAsset,
    "errors": AgentError,
    "alerts": Alert,
}
_DICT_OF_LIST_MODEL_FIELDS: dict[str, type[BaseModel]] = {"assigned_tasks": Task}


def serialize_state(state: MarketingState) -> dict[str, Any]:
    """MarketingState -> dict JSON-compatible (datetime en ISO 8601, modèles
    Pydantic imbriqués via model_dump(mode="json"))."""
    payload: dict[str, Any] = {}
    for key, value in state.items():
        if key in _LIST_MODEL_FIELDS:
            payload[key] = [item.model_dump(mode="json") for item in value]
        elif key in _DICT_OF_LIST_MODEL_FIELDS:
            payload[key] = {k: [item.model_dump(mode="json") for item in v] for k, v in value.items()}
        elif isinstance(value, datetime):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    return payload


def deserialize_state(data: dict[str, Any]) -> MarketingState:
    """dict JSON -> MarketingState (reconstruit les modèles Pydantic imbriqués
    et parse les dates ISO 8601)."""
    payload: dict[str, Any] = {}
    for key, value in data.items():
        if key in _LIST_MODEL_FIELDS and value is not None:
            model_cls = _LIST_MODEL_FIELDS[key]
            payload[key] = TypeAdapter(list[model_cls]).validate_python(value)
        elif key in _DICT_OF_LIST_MODEL_FIELDS and value is not None:
            model_cls = _DICT_OF_LIST_MODEL_FIELDS[key]
            payload[key] = {k: TypeAdapter(list[model_cls]).validate_python(v) for k, v in value.items()}
        elif key in ("period_start", "period_end", "created_at", "last_updated_at") and isinstance(value, str):
            payload[key] = datetime.fromisoformat(value)
        else:
            payload[key] = value
    return MarketingState(**payload)  # type: ignore[typeddict-item]
