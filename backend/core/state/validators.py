"""Validateurs d'état post-fanout : appelés après un Send() parallèle
(validate_parallel_results_node, voir backend/agents/orchestrator/nodes.py,
Prompt 4.2 - pas encore écrit) pour vérifier que tous les agents attendus ont
bien écrit leur résultat, sans bloquer le graphe en cas de champ manquant
(cf. mise_en_place.md : "En cas de champ manquant : ajoute une alerte et
continue sans bloquer").
"""

from pydantic import BaseModel, ConfigDict, Field

from backend.core.state.marketing_state import MarketingState

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# Champs "vides" possibles pour un type donné  sert à détecter qu'un champ
# n'a PAS été rempli par l'agent censé le produire, distinct d'un champ
# rempli mais légitimement vide (ex. seo_keywords=[] parce qu'aucun mot-clé
# n'a été trouvé est un résultat valide, pas une absence de résultat...
# mais pour ce module, on reste volontairement conservateur : un champ
# manquant du dict *ou* laissé à sa valeur par défaut "vide" est traité de
# la même façon, faute de pouvoir distinguer les deux depuis un simple dict.
_EMPTY_SENTINELS: tuple = (None, [], {}, "")


class ValidationResult(BaseModel):
    model_config = _STRICT_CONFIG

    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


def check_required_fields(state: MarketingState, agent_name: str) -> list[str]:
    """Retourne la liste des champs de MarketingState que `agent_name` aurait
    dû remplir et qui sont absents/vides. Le mapping agent -> champs attendus
    reflète les champs "Résultats agents" de marketing_state.py."""
    expected_by_agent: dict[str, list[str]] = {
        "seo": ["seo_keywords", "seo_audit_results"],
        "sea": ["sea_campaigns"],
        "content": ["generated_contents"],
        "social": ["published_contents"],
        "email": ["email_sequences_triggered"],
        "analytics": ["analytics_data", "performance_summary"],
        "reporting": ["performance_summary"],
        "creative": ["visual_assets"],
    }
    expected_fields = expected_by_agent.get(agent_name, [])
    return [field for field in expected_fields if state.get(field) in _EMPTY_SENTINELS]


def validate_parallel_results(state: MarketingState, expected_fields: list[str]) -> ValidationResult:
    """Vérifie qu'aucun champ de `expected_fields` n'est resté vide après un
    fanout parallèle (ex. Acquisition = ["seo_keywords", "sea_campaigns"])."""
    missing = [field for field in expected_fields if state.get(field) in _EMPTY_SENTINELS]
    messages = [f"Champ attendu manquant ou vide après fanout : {field!r}" for field in missing]
    return ValidationResult(valid=not missing, missing_fields=missing, messages=messages)


def validate_budget_not_exceeded(state: MarketingState) -> bool:
    return state.get("budget_consumed", 0.0) <= state.get("budget_total", 0.0)


def validate_iterations_not_exceeded(state: MarketingState) -> bool:
    return state.get("iterations", 0) <= state.get("max_iterations", 0)
