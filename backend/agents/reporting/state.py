"""État du subgraph de l'Agent Reporting  indépendant de MarketingState
(l'Agent Reporting est invocable seul) ; `report_data`/`recommendations`
portent les mêmes noms que ceux échangés avec `measure_cluster.py`
(run_reporting_agent_node envoie `{"analyzed_data": ..., "anomalies": ...,
"client_id": ...}` et lit `result.get("report_data", {})`/
`result.get("recommendations", [])`)."""

from typing import Optional, TypedDict


class ReportingState(TypedDict):
    client_id: str
    # Reçus du cluster Mesure (sortie de l'Agent Analytics)
    analyzed_data: Optional[dict]
    anomalies: list[dict]
    # Optionnel : période explicite ("2026-W10")  dérivée de la date
    # courante si absente (voir load_report_context_node).
    period: Optional[str]
    # Destinataires email du rapport, transmis par l'appelant (deliver_report_node) 
    # liste vide = pas d'envoi email, seulement stockage + exposition API.
    recipient_emails: list[str]

    # Renseigné par load_report_context_node
    kpis: dict
    decisions: list[dict]

    # Renseigné par generate_executive_summary_node
    executive_summary: str

    # Renseigné par generate_channel_breakdown_node
    channel_performance: dict[str, dict]

    # Renseigné par generate_recommendations_node
    recommendations: list[dict]
    next_week_plan: str

    # Renseigné par format_report_node
    weekly_report: Optional[dict]

    # Renseigné par hitl_before_send_node
    approved: bool
    hitl_feedback: Optional[str]

    # Renseigné par deliver_report_node
    report_id: Optional[str]
    report_url: Optional[str]
    delivered: bool

    # Sortie finale (mêmes noms que MeasureState)
    report_data: dict
