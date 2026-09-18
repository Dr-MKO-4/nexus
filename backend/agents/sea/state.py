"""État du subgraph de l'Agent SEA  indépendant de MarketingState (l'Agent
SEA est invocable seul), le champ de sortie `sea_campaigns` porte le même
nom que dans MarketingState pour que acquisition_cluster.run_sea_agent_node
puisse le reporter tel quel.
"""

from typing import Optional, TypedDict

from backend.agents.sea.budget_manager import CampaignBudgetInfo, PacingStatus
from backend.core.state.state_models import Alert, CampaignConfig


class SEAState(TypedDict):
    client_id: str
    # Reçu de l'Orchestrateur/du cluster Acquisition : {"objective": str, "budget": float}
    brief: Optional[dict]

    # Renseigné par load_sea_context_node
    active_campaigns: list[CampaignConfig]
    campaign_budgets: list[CampaignBudgetInfo]
    # Historique des campagnes du client (au-delà des seules campagnes actives)  spec 5.2 :
    # "load_sea_context : charge les campagnes actives et l'historique"
    campaign_history: list[dict]
    customer_id: Optional[str]  # Google Ads
    account_id: Optional[str]  # Meta Ads

    # Renseigné par analyze_performance_node
    performance_analysis: Optional[dict]

    # Renseigné par optimize_bids_node
    bid_adjustments: list[dict]

    # Renseigné par generate_ad_variants_node
    ad_variants: list[dict]

    # Renseigné par manage_budget_node
    budget_allocation: dict[str, float]
    pacing_status: Optional[PacingStatus]

    # Renseigné par detect_anomalies_node
    overspending_alerts: list[Alert]

    # Sortie finale (même nom que MarketingState)
    sea_campaigns: list[CampaignConfig]
