"""État du subgraph de l'Agent Social  indépendant de MarketingState (l'Agent
Social est invocable seul) ; `contents`/`published_contents` portent les
mêmes noms/formats que ceux échangés avec `engagement_cluster.py`
(run_social_agent_node envoie `{"contents": [...], "client_id": ...}` et lit
`result.get("published_contents", [])`).
"""

from typing import Optional, TypedDict

from backend.core.state.state_models import Alert, Content


class SocialState(TypedDict):
    client_id: str
    # Contenus à publier, produits par l'Agent Content (platform in
    # linkedin/meta/tiktok  voir engagement_cluster.distribute_to_channels_node).
    contents: list[Content]

    # Renseigné par load_social_context_node
    recent_engagement_metrics: list[dict]
    existing_calendar: list[dict]
    # Tendances détectées lors d'une exécution précédente (persistées par
    # detect_trends_node via AgentDecisionRepository)  évite de
    # re-suggérer les mêmes tendances d'une exécution à l'autre.
    previously_detected_trends: list[dict]
    client_name: Optional[str]
    industry: Optional[str]

    # Renseigné par adapt_content_per_platform_node
    adapted_posts: list[dict]

    # Renseigné par schedule_publications_node
    publication_schedule: list[dict]

    # Renseigné par publish_content_node
    publish_results: list[dict]
    published_contents: list[str]

    # Renseigné par monitor_engagement_node
    engagement_metrics: list[dict]

    # Renseigné par detect_trends_node
    detected_trends: list[dict]
    detected_mentions: list[dict]

    # Renseigné par sentiment_analysis_node
    sentiment_results: list[dict]

    # Renseigné par crisis_detector_node
    crisis_alerts: list[Alert]

    # Renseigné par social_reporter_node
    social_report: Optional[dict]
