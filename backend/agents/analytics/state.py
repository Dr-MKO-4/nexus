"""État du subgraph de l'Agent Analytics  indépendant de MarketingState
(l'Agent Analytics est invocable seul) ; `raw_metrics`/`analyzed_data`
portent les mêmes noms que ceux échangés avec `measure_cluster.py`
(run_analytics_agent_node envoie `{"raw_metrics": ..., "client_id": ...}` et
lit `result.get("analyzed_data", {}).get("kpis", {})`  `analyzed_data` doit
donc toujours être un dict, jamais None).
"""

from typing import Optional, TypedDict


class AnalyticsState(TypedDict):
    client_id: str
    # Reçu du cluster Mesure (déjà partiellement peuplé par
    # collect_all_metrics_node du cluster)  l'agent standalone recharge/
    # complète lui-même via ses propres nœuds collect_*.
    raw_metrics: Optional[dict]

    # Renseigné par collect_matomo_data_node
    matomo_data: dict

    # Renseigné par collect_campaign_data_node
    campaign_data: dict

    # Renseigné par collect_email_data_node
    email_data: dict

    # Renseigné par collect_social_data_node
    social_data: dict

    # Renseigné par compute_kpis_node
    kpis: dict[str, float]

    # Renseigné par detect_anomalies_pytorch_node
    anomalies: list[dict]

    # Renseigné par attribution_analysis_node
    attribution: dict[str, float]

    # Renseigné par generate_insights_node
    insights: list[dict]
    recommendations: list[dict]

    # Renseigné par store_metrics_node
    metrics_stored: bool

    # Sortie finale (même nom que MeasureState.analyzed_data)
    analyzed_data: dict
