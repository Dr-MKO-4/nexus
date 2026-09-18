"""État du subgraph de l'Agent Creative  indépendant de MarketingState
(l'Agent Creative est invocable seul) ; `visual_assets` porte le même nom
que dans MarketingState."""

from typing import Optional, TypedDict

from backend.core.state.state_models import VisualAsset


class CreativeState(TypedDict):
    client_id: str
    # Reçu de l'Orchestrateur/du cluster : {"brief_text": str, "content_type": str,
    # "platform": str, "dimensions": str | None, "campaign_id": str | None}
    brief: Optional[dict]

    # Renseigné par receive_brief_node
    parsed_brief: Optional[dict]

    # Renseigné par select_template_node
    selected_template: Optional[dict]

    # Renseigné par retrieve_style_references_node
    style_references: list[dict]
    ipadapter_inputs: list[str]

    # Renseigné par prepare_comfyui_workflow_node
    controlnet_guidance_path: Optional[str]
    generation_prompt: Optional[str]
    negative_prompt: Optional[str]
    workflow_json: Optional[dict]

    # Renseigné par generate_visual_node
    prompt_id: Optional[str]
    raw_image_paths: list[str]

    # Renseigné par evaluate_visual_node
    quality_evaluation: Optional[dict]

    # Renseigné par post_process_node
    final_image_paths: list[str]
    upscaled: bool

    # Renseigné par store_visual_node
    stored_visual_id: Optional[str]

    # Sortie finale (même nom que MarketingState)
    visual_assets: list[VisualAsset]
