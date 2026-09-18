"""État du subgraph de l'Agent Content  indépendant de MarketingState (l'Agent
Content est invocable seul) ; le champ de sortie `generated_contents` porte le
même nom que dans MarketingState pour que le cluster appelant puisse le
reporter tel quel.
"""

from typing import Optional, TypedDict

from backend.core.state.state_models import Content

DEFAULT_MAX_ITERATIONS = 3


class ContentState(TypedDict):
    client_id: str
    # Reçu de l'Orchestrateur/du cluster : {"objective": str, "content_type": str,
    # "platform": str, "target_keywords": list[str], "target_audience": str, "campaign_id": str | None}
    brief: Optional[dict]

    # Renseigné par load_content_context_node
    editorial_guidelines: Optional[dict]
    similar_contents: list[dict]

    # Renseigné par select_template_node
    selected_template: Optional[dict]

    # Renseigné par generate_draft_node (ContentDraft), incrémenté à chaque appel
    draft: Optional[dict]
    iterations: int
    max_iterations: int

    # Renseigné par evaluate_quality_node (PyTorch ContentScorer + jugement LLM)
    quality_evaluation: Optional[dict]

    # Renseigné par evaluate_seo_score_node
    seo_score: Optional[float]

    # Renseigné par finalize_content_node
    final_content: Optional[dict]
    needs_human_review: bool

    # Renseigné par store_content_node
    stored_content_id: Optional[str]

    # Sortie finale (même nom que MarketingState)
    generated_contents: list[Content]
