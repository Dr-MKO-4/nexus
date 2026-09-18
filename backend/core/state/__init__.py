"""Définition et gestion de l'état partagé entre les agents durant une session de travail."""

from backend.core.state.marketing_state import DEFAULT_MAX_ITERATIONS, MarketingState
from backend.core.state.state_manager import (
    BudgetStatus,
    StateValidationError,
    check_budget_status,
    create_initial_state,
    deserialize_state,
    get_state_summary,
    merge_parallel_results,
    serialize_state,
    validate_state,
)
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
from backend.core.state.validators import (
    ValidationResult,
    check_required_fields,
    validate_budget_not_exceeded,
    validate_iterations_not_exceeded,
    validate_parallel_results,
)

__all__ = [
    "MarketingState",
    "DEFAULT_MAX_ITERATIONS",
    # state_models
    "PlanItem",
    "Task",
    "HITLRequest",
    "Keyword",
    "CampaignConfig",
    "Content",
    "VisualAsset",
    "AgentError",
    "Alert",
    # state_manager
    "create_initial_state",
    "validate_state",
    "StateValidationError",
    "get_state_summary",
    "merge_parallel_results",
    "check_budget_status",
    "BudgetStatus",
    "serialize_state",
    "deserialize_state",
    # validators
    "validate_parallel_results",
    "check_required_fields",
    "validate_budget_not_exceeded",
    "validate_iterations_not_exceeded",
    "ValidationResult",
]
