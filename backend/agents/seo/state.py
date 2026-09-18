"""État du subgraph de l'Agent SEO  indépendant de MarketingState (l'Agent
SEO est invocable seul, pas uniquement depuis acquisition_cluster.py) ; les
champs de sortie (`seo_keywords`, `seo_audit_results`) portent les mêmes noms
que dans MarketingState pour que acquisition_cluster.run_seo_agent_node
puisse les reporter tels quels.
"""

from typing import Optional, TypedDict

from backend.core.state.state_models import Keyword


class SEOState(TypedDict):
    client_id: str
    # Reçu de l'Orchestrateur/du cluster Acquisition : {"objective": str, "budget": float}
    brief: Optional[dict]

    # Renseigné par load_seo_context_node
    existing_keywords: list[Keyword]
    site_url: Optional[str]
    industry: Optional[str]
    editorial_context: Optional[str]

    # Renseigné par research_keywords_node
    keyword_candidates: list[dict]

    # Renseigné par analyze_competitors_node
    competitor_analysis: Optional[dict]

    # Renseigné par generate_briefs_node
    content_briefs: list[dict]

    # Sorties finales (mêmes noms que MarketingState)
    seo_keywords: list[Keyword]
    seo_audit_results: Optional[dict]
