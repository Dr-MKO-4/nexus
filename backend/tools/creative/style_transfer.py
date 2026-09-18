"""Gestionnaire de transfert de style  Prompt 5.7."""

import hashlib
from pathlib import Path
from uuid import uuid4

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.tools.creative.figma_client import TemplateStructure

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# Dossier local des références/guidances téléchargées/générées  même
# convention que backend/pytorch_models/checkpoints/ (chemin relatif au
# process, gitignoré) : ces fichiers sont des artefacts régénérables, pas du
# code source.
_ASSETS_DIR = Path("data/creative_assets")


class StyleReference(BaseModel):
    model_config = _STRICT_CONFIG

    point_id: str
    file_path: str
    style_tags: list[str] = Field(default_factory=list)
    score: float


async def get_style_references(brief_text: str, client_id: str, n: int = 5) -> list[StyleReference]:
    """Interroge Qdrant COLLECTION_VISUAL_REFERENCES (via
    semantic_search.search_visual_references, déjà l'espace CLIP partagé
    image/texte  Prompt 2.3) pour les références visuelles les plus
    pertinentes au brief."""
    try:
        from backend.core.memory.semantic_search import search_visual_references

        results = await search_visual_references(brief_text, client_id, limit=n)
    except Exception as exc:
        logger.warning("style_transfer.get_style_references_failed", client_id=client_id, error=str(exc))
        return []

    references = [
        StyleReference(point_id=r.point_id, file_path=r.file_path or "", style_tags=r.style_tags or [], score=r.score)
        for r in results
        if r.file_path
    ]
    logger.info("style_transfer.style_references_fetched", client_id=client_id, reference_count=len(references))
    return references


def prepare_ipadapter_inputs(references: list[StyleReference]) -> list[str]:
    """Chemins d'images à fournir à l'IPAdapter (ComfyUI)  simple
    projection sur `file_path`, dans l'ordre de pertinence déjà trié par
    Qdrant (score décroissant)."""
    return [ref.file_path for ref in references if ref.file_path]


def build_controlnet_guidance(template_structure: TemplateStructure) -> str:
    """Génère une image de guidance (fond noir, zones de texte en gris,
    zones d'image en blanc) depuis la structure du template  convention
    standard pour un ControlNet de type "layout"/segmentation grossière,
    cohérente avec `comfyui_client.build_flux_workflow`'s paramètre
    `controlnet_image_path`."""
    from PIL import Image, ImageDraw

    width = max(int(template_structure.width), 1)
    height = max(int(template_structure.height), 1)
    image = Image.new("L", (width, height), color=0)
    draw = ImageDraw.Draw(image)

    for zone in template_structure.text_zones:
        box = _zone_box(zone, template_structure)
        draw.rectangle(box, fill=128)
    for zone in template_structure.image_zones:
        box = _zone_box(zone, template_structure)
        draw.rectangle(box, fill=255)

    _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _ASSETS_DIR / f"controlnet_guidance_{template_structure.frame_id}_{uuid4().hex[:8]}.png"
    image.save(output_path)

    logger.info("style_transfer.controlnet_guidance_built", frame_id=template_structure.frame_id, path=str(output_path))
    return str(output_path)


def _zone_box(zone: dict, template_structure: TemplateStructure) -> tuple[int, int, int, int]:
    x0 = max(int(zone.get("x", 0)), 0)
    y0 = max(int(zone.get("y", 0)), 0)
    x1 = min(int(zone.get("x", 0) + zone.get("width", 0)), int(template_structure.width))
    y1 = min(int(zone.get("y", 0) + zone.get("height", 0)), int(template_structure.height))
    return (x0, y0, max(x1, x0 + 1), max(y1, y0 + 1))


async def upload_reference(image_path: str, client_id: str, style_tags: list[str]) -> str:
    """Embed `image_path` avec CLIP et stocke dans Qdrant
    COLLECTION_VISUAL_REFERENCES (espace image/texte partagé  voir
    embedding_manager.ImageEmbedder, Prompt 2.3)."""
    from backend.core.memory.collections import COLLECTION_VISUAL_REFERENCES
    from backend.core.memory.embedding_manager import ImageEmbedder
    from backend.core.memory.qdrant_client import get_qdrant_client

    vector = await ImageEmbedder().embed_image(image_path)
    point_id = hashlib.sha256(f"{client_id}:{image_path}".encode()).hexdigest()[:32]
    point_id = f"{point_id[:8]}-{point_id[8:12]}-{point_id[12:16]}-{point_id[16:20]}-{point_id[20:32]}"

    await get_qdrant_client().upsert(
        COLLECTION_VISUAL_REFERENCES.name,
        point_id,
        vector,
        {
            "client_id": client_id,
            "visual_type": "reference",
            "style_tags": style_tags,
            "file_path": image_path,
            "usage_count": 0,
        },
    )
    logger.info("style_transfer.reference_uploaded", client_id=client_id, point_id=point_id, image_path=image_path)
    return point_id


__all__ = ["StyleReference", "get_style_references", "prepare_ipadapter_inputs", "build_controlnet_guidance", "upload_reference"]
