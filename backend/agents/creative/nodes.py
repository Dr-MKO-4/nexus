"""Implémentation des nœuds de l'Agent Creative.

Génération de prompt avec Qwen3.5 72B (task_type="creative", voir
hybrid_router.TASK_TYPE_TO_LOCAL_MODEL) via `NexusLLMClient.complete_structured`.
"""

import json
from uuid import uuid4

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.agents.creative.prompts import get_creative_prompt
from backend.agents.creative.state import CreativeState
from backend.core.state.state_models import VisualAsset
from backend.llm.gateway.llm_client import NexusLLMClient
from backend.tools.creative.comfyui_client import ComfyUIClient
from backend.tools.creative.figma_client import FigmaClient, list_client_templates
from backend.tools.creative.style_transfer import (
    build_controlnet_guidance,
    get_style_references,
    prepare_ipadapter_inputs,
    upload_reference,
)

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# Structure par défaut quand aucun ContentTemplate client n'a de
# figma_file_id  même principe que agents.content.nodes._DEFAULT_STRUCTURES :
# repli documenté, pas une donnée inventée silencieusement.
_DEFAULT_DIMENSIONS = {"post": "1080x1080", "story": "1080x1920", "banner": "1200x628", "landing_page": "1920x1080"}

# Seuil de score en-dessous duquel evaluate_visual_node demande un upscale
# (post_process_node)  le spec dit "upscale avec Real-ESRGAN si nécessaire"
# sans préciser le critère ; résolu ici sur la dimension cible vs. la
# résolution native du modèle de diffusion (1024, voir lora_trainer.py),
# pas sur le score qualité (qui évalue la cohérence, pas la résolution).
_UPSCALE_MIN_DIMENSION = 1536
_FALLBACK_DIMENSIONS = (1080, 1080)


def _parse_dimensions(dimensions: str) -> tuple[int, int]:
    """Parse une chaîne "WxH" en (width, height) ; repli sur
    `_FALLBACK_DIMENSIONS` si le format est inattendu (ex. valeur fournie
    par un appelant externe via `brief["dimensions"]`, jamais validée en
    amont)  mieux vaut une image au format par défaut qu'un nœud entier qui
    plante sur un `ValueError` de parsing."""
    try:
        width_str, height_str = dimensions.split("x")
        return int(width_str), int(height_str)
    except (ValueError, AttributeError):
        logger.warning("creative_nodes.invalid_dimensions_fallback", dimensions=dimensions, fallback=_FALLBACK_DIMENSIONS)
        return _FALLBACK_DIMENSIONS


class ParsedBrief(BaseModel):
    model_config = _STRICT_CONFIG

    subject: str
    style_keywords: list[str] = Field(default_factory=list)
    mood: str = ""
    key_elements: list[str] = Field(default_factory=list)


class VisualGenerationPromptResult(BaseModel):
    model_config = _STRICT_CONFIG

    prompt: str
    negative_prompt: str


class VisualEvaluation(BaseModel):
    model_config = _STRICT_CONFIG

    score: float = Field(ge=0, le=1)
    text_legible_estimate: str
    structure_respected_estimate: str
    feedback: str


async def receive_brief_node(state: CreativeState) -> dict:
    """Parse et valide le brief visuel reçu (BRIEF_PARSER_PROMPT)."""
    client_id = state["client_id"]
    brief = state.get("brief") or {}
    brief_text = brief.get("brief_text", "")

    if not brief_text.strip():
        logger.warning("creative_nodes.empty_brief", client_id=client_id)
        return {"parsed_brief": {"subject": "", "style_keywords": [], "mood": "", "key_elements": []}}

    llm_client = NexusLLMClient()
    try:
        prompt = get_creative_prompt(
            "creative-brief-parser",
            brief_text=brief_text,
            content_type=brief.get("content_type", "visual"),
            platform=brief.get("platform", "non précisée"),
        )
        parsed = await llm_client.complete_structured(
            prompt=prompt, response_model=ParsedBrief, task_type="creative", client_id=client_id, agent_name="creative"
        )
        result = parsed.model_dump()
    except Exception as exc:
        logger.warning("creative_nodes.brief_parsing_failed", client_id=client_id, error=str(exc))
        result = {"subject": brief_text[:200], "style_keywords": [], "mood": "", "key_elements": []}

    logger.info("creative_nodes.brief_received", client_id=client_id, subject=result.get("subject"))
    return {"parsed_brief": result}


async def select_template_node(state: CreativeState) -> dict:
    """Sélectionne le template Figma/Canva approprié  un ContentTemplate
    client en base (figma_file_id) a priorité sur un repli de dimensions par
    défaut selon le type de contenu."""
    client_id = state["client_id"]
    brief = state.get("brief") or {}
    content_type = brief.get("content_type", "post")

    templates = await list_client_templates(client_id)
    matching = [t for t in templates if t.template_type == content_type and t.figma_file_id]

    if matching:
        selected = matching[0].model_dump()
        logger.info("creative_nodes.template_selected", client_id=client_id, source="figma", figma_file_id=selected.get("figma_file_id"))
    else:
        dimensions = brief.get("dimensions") or _DEFAULT_DIMENSIONS.get(content_type, "1080x1080")
        selected = {"template_type": content_type, "figma_file_id": None, "canva_template_id": None, "structure": {"dimensions": dimensions}}
        logger.info("creative_nodes.template_selected", client_id=client_id, source="default", dimensions=dimensions)

    return {"selected_template": selected}


async def retrieve_style_references_node(state: CreativeState) -> dict:
    """Interroge Qdrant pour les références visuelles les plus pertinentes
    (IPAdapter inputs)."""
    client_id = state["client_id"]
    parsed_brief = state.get("parsed_brief") or {}
    brief_text = " ".join([parsed_brief.get("subject", ""), *parsed_brief.get("style_keywords", [])]).strip()
    brief_text = brief_text or (state.get("brief") or {}).get("brief_text", "")

    references = await get_style_references(brief_text, client_id, n=5) if brief_text else []
    ipadapter_inputs = prepare_ipadapter_inputs(references)

    logger.info("creative_nodes.style_references_retrieved", client_id=client_id, reference_count=len(references))
    return {"style_references": [r.model_dump() for r in references], "ipadapter_inputs": ipadapter_inputs}


async def prepare_comfyui_workflow_node(state: CreativeState) -> dict:
    """Construit le workflow ComfyUI JSON : guidance ControlNet depuis la
    structure du template (si un fichier Figma est associé), prompt de
    génération via VISUAL_GENERATION_PROMPT, puis assemblage du workflow
    (comfyui_client.build_flux_workflow)."""
    client_id = state["client_id"]
    selected_template = state.get("selected_template") or {}
    parsed_brief = state.get("parsed_brief") or {}
    ipadapter_inputs = state.get("ipadapter_inputs") or []

    controlnet_guidance_path: str | None = None
    template_structure_summary = "aucune (pas de fichier Figma associé à ce template)"
    figma_file_id = selected_template.get("figma_file_id")
    if figma_file_id:
        try:
            figma_client = FigmaClient()
            try:
                # frame_id : premier frame de niveau racine du fichier  le
                # spec ne précise pas comment le choisir parmi plusieurs
                # frames possibles ; repli documenté sur le premier trouvé.
                file = await figma_client.get_file(figma_file_id)
                root_children = file.document.get("children", [])
                frame_id = root_children[0]["id"] if root_children else None
                if frame_id:
                    structure = await figma_client.extract_template_structure(figma_file_id, frame_id)
                    controlnet_guidance_path = build_controlnet_guidance(structure)
                    template_structure_summary = f"{structure.width}x{structure.height}, {len(structure.text_zones)} zone(s) de texte, {len(structure.image_zones)} zone(s) d'image"
            finally:
                await figma_client.aclose()
        except RuntimeError as exc:
            logger.warning("creative_nodes.figma_unconfigured", client_id=client_id, error=str(exc))
        except Exception as exc:
            logger.warning("creative_nodes.template_structure_extraction_failed", client_id=client_id, error=str(exc))

    llm_client = NexusLLMClient()
    generation_prompt, negative_prompt = "", ""
    try:
        prompt = get_creative_prompt(
            "creative-visual-generation",
            parsed_brief=json.dumps(parsed_brief, ensure_ascii=False),
            style_references=json.dumps(state.get("style_references") or [], ensure_ascii=False),
            template_structure=template_structure_summary,
        )
        result = await llm_client.complete_structured(
            prompt=prompt,
            response_model=VisualGenerationPromptResult,
            task_type="creative",
            client_id=client_id,
            agent_name="creative",
        )
        generation_prompt, negative_prompt = result.prompt, result.negative_prompt
    except Exception as exc:
        logger.warning("creative_nodes.prompt_generation_failed", client_id=client_id, error=str(exc))
        generation_prompt = parsed_brief.get("subject", "") or "product marketing visual"
        negative_prompt = "blurry, low quality, watermark, text artifacts"

    dimensions = (selected_template.get("structure") or {}).get("dimensions", "1080x1080")
    width, height = _parse_dimensions(dimensions)

    comfyui_client = ComfyUIClient()
    workflow_json = comfyui_client.build_flux_workflow(
        generation_prompt, negative_prompt, width, height, ipadapter_inputs, controlnet_guidance_path
    )

    logger.info("creative_nodes.workflow_prepared", client_id=client_id, width=width, height=height)
    return {
        "controlnet_guidance_path": controlnet_guidance_path,
        "generation_prompt": generation_prompt,
        "negative_prompt": negative_prompt,
        "workflow_json": workflow_json,
    }


async def generate_visual_node(state: CreativeState) -> dict:
    """Soumet le workflow à ComfyUI et attend le résultat."""
    client_id = state["client_id"]
    workflow_json = state.get("workflow_json")
    if not workflow_json:
        logger.warning("creative_nodes.no_workflow_to_submit", client_id=client_id)
        return {"prompt_id": None, "raw_image_paths": []}

    comfyui_client = ComfyUIClient()
    try:
        prompt_id = await comfyui_client.submit_workflow(workflow_json)
        image_paths = await comfyui_client.wait_for_completion(prompt_id, timeout=300)
    except Exception as exc:
        logger.warning("creative_nodes.generation_failed", client_id=client_id, error=str(exc))
        return {"prompt_id": None, "raw_image_paths": []}
    finally:
        await comfyui_client.aclose()

    logger.info("creative_nodes.visual_generated", client_id=client_id, prompt_id=prompt_id, image_count=len(image_paths))
    return {"prompt_id": prompt_id, "raw_image_paths": image_paths}


async def evaluate_visual_node(state: CreativeState) -> dict:
    """Évalue la qualité (texte lisible, structure respectée)  limite
    documentée : aucun modèle multimodal n'est branché dans ce gateway LLM
    (LiteLLM/instructor, texte uniquement), l'évaluation se fait donc sur les
    métadonnées et la cohérence du prompt soumis, pas sur une analyse
    visuelle réelle du pixel (voir VISUAL_EVALUATION_PROMPT)."""
    client_id = state["client_id"]
    parsed_brief = state.get("parsed_brief") or {}
    raw_image_paths = state.get("raw_image_paths") or []

    if not raw_image_paths:
        return {"quality_evaluation": {"score": 0.0, "text_legible_estimate": "improbable", "structure_respected_estimate": "improbable", "feedback": "Aucune image générée."}}

    llm_client = NexusLLMClient()
    try:
        prompt = get_creative_prompt(
            "creative-visual-evaluation",
            parsed_brief=json.dumps(parsed_brief, ensure_ascii=False),
            visual_metadata=json.dumps(
                {"image_paths": raw_image_paths, "prompt": state.get("generation_prompt", "")}, ensure_ascii=False
            ),
        )
        evaluation = await llm_client.complete_structured(
            prompt=prompt, response_model=VisualEvaluation, task_type="creative", client_id=client_id, agent_name="creative"
        )
        result = evaluation.model_dump()
    except Exception as exc:
        logger.warning("creative_nodes.evaluation_failed", client_id=client_id, error=str(exc))
        result = {"score": 0.5, "text_legible_estimate": "incertain", "structure_respected_estimate": "incertain", "feedback": "Évaluation indisponible."}

    logger.info("creative_nodes.visual_evaluated", client_id=client_id, score=result.get("score"))
    return {"quality_evaluation": result}


async def post_process_node(state: CreativeState) -> dict:
    """Upscale avec Real-ESRGAN (via ComfyUI, voir comfyui_client.py) si la
    dimension cible dépasse la résolution native du modèle de diffusion."""
    client_id = state["client_id"]
    raw_image_paths = state.get("raw_image_paths") or []
    selected_template = state.get("selected_template") or {}
    dimensions = (selected_template.get("structure") or {}).get("dimensions", "1080x1080")
    max_dimension = max(_parse_dimensions(dimensions))

    if not raw_image_paths or max_dimension < _UPSCALE_MIN_DIMENSION:
        return {"final_image_paths": raw_image_paths, "upscaled": False}

    comfyui_client = ComfyUIClient()
    final_paths: list[str] = []
    try:
        for image_path in raw_image_paths:
            workflow = comfyui_client.build_upscale_workflow(image_path)
            prompt_id = await comfyui_client.submit_workflow(workflow)
            upscaled_paths = await comfyui_client.wait_for_completion(prompt_id, timeout=180)
            final_paths.extend(upscaled_paths or [image_path])
    except Exception as exc:
        logger.warning("creative_nodes.upscale_failed", client_id=client_id, error=str(exc))
        return {"final_image_paths": raw_image_paths, "upscaled": False}
    finally:
        await comfyui_client.aclose()

    logger.info("creative_nodes.post_processed", client_id=client_id, upscaled_count=len(final_paths))
    return {"final_image_paths": final_paths, "upscaled": True}


async def store_visual_node(state: CreativeState) -> dict:
    """Sauvegarde dans le filesystem (déjà fait par ComfyUI lui-même  voir
    comfyui_client.get_output_images) + Qdrant (embedding CLIP)."""
    client_id = state["client_id"]
    final_image_paths = state.get("final_image_paths") or []
    parsed_brief = state.get("parsed_brief") or {}
    style_tags = parsed_brief.get("style_keywords", [])

    stored_visual_id: str | None = None
    if final_image_paths:
        try:
            stored_visual_id = await upload_reference(final_image_paths[0], client_id, style_tags)
        except Exception as exc:
            logger.warning("creative_nodes.store_visual_failed", client_id=client_id, error=str(exc))

    logger.info("creative_nodes.visual_stored", client_id=client_id, stored_visual_id=stored_visual_id)
    return {"stored_visual_id": stored_visual_id}


async def creative_reporter_node(state: CreativeState) -> dict:
    """Retourne le chemin du visuel et les métadonnées à l'orchestrateur/cluster appelant."""
    final_image_paths = state.get("final_image_paths") or []
    selected_template = state.get("selected_template") or {}
    parsed_brief = state.get("parsed_brief") or {}
    dimensions = (selected_template.get("structure") or {}).get("dimensions", "1080x1080")

    visual_assets = [
        VisualAsset(
            id=str(uuid4()),
            type="image",
            format="png",
            file_path=path,
            dimensions=dimensions,
            style_tags=parsed_brief.get("style_keywords", []),
        )
        for path in final_image_paths
    ]

    logger.info("creative_nodes.completed", client_id=state["client_id"], visual_count=len(visual_assets))
    return {"visual_assets": visual_assets}
