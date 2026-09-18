"""État du subgraph de l'Agent Email  indépendant de MarketingState (l'Agent
Email est invocable seul) ; `contents`/`email_sequences_triggered` portent
les mêmes noms/formats que ceux échangés avec `engagement_cluster.py`
(run_email_agent_node envoie `{"contents": [...], "client_id": ...}` et lit
`result.get("email_sequences_triggered", [])`).
"""

from typing import Optional, TypedDict

from backend.core.state.state_models import Content
from backend.tools.email.mautic_client import Contact


class EmailState(TypedDict):
    client_id: str
    # Contenus email ponctuels reçus de l'Agent Content (platform="email",
    # ex. newsletter)  utilisés comme contexte produit pour les séquences,
    # indépendants du pipeline de séquences comportementales lui-même.
    contents: list[Content]

    # Renseigné par load_email_context_node
    contacts: list[Contact]
    sequence_history: list[dict]
    open_click_rates: dict

    # Renseigné par segment_audience_node
    segments: dict[str, list[dict]]

    # Renseigné par select_sequence_node
    selected_sequences: list[dict]

    # Renseigné par generate_email_content_node
    email_drafts: list[dict]

    # Renseigné par optimize_subject_lines_node
    subject_line_variants: list[dict]

    # Renseigné par schedule_send_node
    send_schedule: list[dict]

    # Renseigné par trigger_mautic_node
    trigger_results: list[dict]
    email_sequences_triggered: list[str]

    # Renseigné par track_results_node
    tracked_metrics: list[dict]

    # Renseigné par email_reporter_node
    email_report: Optional[dict]
