"""Client Figma API  Prompt 5.7.

Authentification par token personnel (`settings.FIGMA_ACCESS_TOKEN`, header
`X-Figma-Token`)  credential applicative globale, même limite structurelle
documentée pour les autres intégrations tierces de ce projet (Google Ads,
Mautic...).

Endpoints REST Figma réels utilisés :
- `GET /v1/files/{file_key}`  arbre de nœuds complet du fichier.
- `GET /v1/files/{file_key}/components`  composants publiés (bibliothèque).
- `GET /v1/images/{file_key}?ids=...&format=...&scale=...`  ne retourne que
  des URLs S3 temporaires, pas les bytes directement : `export_frame`
  effectue un second appel HTTP (hors API Figma) pour télécharger l'image.
"""

from uuid import UUID

import structlog
import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
_API_BASE = "https://api.figma.com/v1"


class FigmaFile(BaseModel):
    model_config = _STRICT_CONFIG

    file_key: str
    name: str
    last_modified: str
    document: dict = Field(description="Arbre de nœuds brut (structure Figma), traversé par extract_template_structure.")


class FigmaComponent(BaseModel):
    model_config = _STRICT_CONFIG

    key: str
    name: str
    node_id: str
    description: str = ""


class TemplateStructure(BaseModel):
    model_config = _STRICT_CONFIG

    frame_id: str
    width: float
    height: float
    text_zones: list[dict] = Field(default_factory=list, description="[{node_id, name, x, y, width, height, characters}]")
    image_zones: list[dict] = Field(default_factory=list, description="[{node_id, name, x, y, width, height}]")
    colors: list[str] = Field(default_factory=list, description="Couleurs hex dominantes trouvées dans le frame.")


class Template(BaseModel):
    model_config = _STRICT_CONFIG

    id: str
    client_id: str
    template_type: str
    figma_file_id: str | None = None
    canva_template_id: str | None = None
    structure: dict = Field(default_factory=dict)


def _rgba_to_hex(color: dict) -> str:
    r, g, b = (round(color.get(c, 0) * 255) for c in ("r", "g", "b"))
    return f"#{r:02x}{g:02x}{b:02x}"


def _find_node(node: dict, node_id: str) -> dict | None:
    if node.get("id") == node_id:
        return node
    for child in node.get("children", []):
        found = _find_node(child, node_id)
        if found is not None:
            return found
    return None


def _collect_zones_and_colors(node: dict, text_zones: list[dict], image_zones: list[dict], colors: set[str]) -> None:
    node_type = node.get("type")
    bbox = node.get("absoluteBoundingBox", {})

    if node_type == "TEXT":
        text_zones.append(
            {
                "node_id": node.get("id"),
                "name": node.get("name"),
                "x": bbox.get("x", 0),
                "y": bbox.get("y", 0),
                "width": bbox.get("width", 0),
                "height": bbox.get("height", 0),
                "characters": node.get("characters", ""),
            }
        )
    elif node_type in ("RECTANGLE", "IMAGE") and any(f.get("type") == "IMAGE" for f in node.get("fills", []) or []):
        image_zones.append(
            {
                "node_id": node.get("id"),
                "name": node.get("name"),
                "x": bbox.get("x", 0),
                "y": bbox.get("y", 0),
                "width": bbox.get("width", 0),
                "height": bbox.get("height", 0),
            }
        )

    for fill in node.get("fills", []) or []:
        if fill.get("type") == "SOLID" and "color" in fill:
            colors.add(_rgba_to_hex(fill["color"]))

    for child in node.get("children", []):
        _collect_zones_and_colors(child, text_zones, image_zones, colors)


class FigmaClient:
    def __init__(self, timeout: float = 30.0) -> None:
        if not settings.FIGMA_ACCESS_TOKEN:
            raise RuntimeError("FIGMA_ACCESS_TOKEN doit être configuré dans settings pour utiliser FigmaClient.")
        self._client = httpx.AsyncClient(
            base_url=_API_BASE, headers={"X-Figma-Token": settings.FIGMA_ACCESS_TOKEN}, timeout=timeout
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_file(self, file_key: str) -> FigmaFile:
        response = await self._client.get(f"/files/{file_key}")
        response.raise_for_status()
        body = response.json()
        file = FigmaFile(
            file_key=file_key,
            name=body.get("name", ""),
            last_modified=body.get("lastModified", ""),
            document=body.get("document", {}),
        )
        logger.info("figma_client.file_fetched", file_key=file_key, name=file.name)
        return file

    async def get_components(self, file_key: str) -> list[FigmaComponent]:
        response = await self._client.get(f"/files/{file_key}/components")
        response.raise_for_status()
        components_data = response.json().get("meta", {}).get("components", [])
        components = [
            FigmaComponent(
                key=c.get("key", ""),
                name=c.get("name", ""),
                node_id=c.get("node_id", ""),
                description=c.get("description", ""),
            )
            for c in components_data
        ]
        logger.info("figma_client.components_fetched", file_key=file_key, component_count=len(components))
        return components

    async def export_frame(self, file_key: str, node_id: str, format: str = "PNG", scale: int = 2) -> bytes:
        response = await self._client.get(
            f"/images/{file_key}", params={"ids": node_id, "format": format.lower(), "scale": scale}
        )
        response.raise_for_status()
        image_url = response.json().get("images", {}).get(node_id)
        if not image_url:
            raise RuntimeError(f"Figma n'a retourné aucune URL d'export pour le nœud {node_id!r} (fichier {file_key!r}).")

        async with httpx.AsyncClient(timeout=30.0) as download_client:
            image_response = await download_client.get(image_url)
            image_response.raise_for_status()
            image_bytes = image_response.content

        logger.info("figma_client.frame_exported", file_key=file_key, node_id=node_id, byte_count=len(image_bytes))
        return image_bytes

    async def extract_template_structure(self, file_key: str, frame_id: str) -> TemplateStructure:
        file = await self.get_file(file_key)
        frame_node = _find_node(file.document, frame_id)
        if frame_node is None:
            raise ValueError(f"Nœud {frame_id!r} introuvable dans le fichier Figma {file_key!r}.")

        text_zones: list[dict] = []
        image_zones: list[dict] = []
        colors: set[str] = set()
        _collect_zones_and_colors(frame_node, text_zones, image_zones, colors)

        bbox = frame_node.get("absoluteBoundingBox", {})
        structure = TemplateStructure(
            frame_id=frame_id,
            width=bbox.get("width", 0),
            height=bbox.get("height", 0),
            text_zones=text_zones,
            image_zones=image_zones,
            colors=sorted(colors),
        )
        logger.info(
            "figma_client.template_structure_extracted",
            file_key=file_key,
            frame_id=frame_id,
            text_zone_count=len(text_zones),
            image_zone_count=len(image_zones),
        )
        return structure

    async def list_client_templates(self, client_id: str) -> list[Template]:
        """Délègue à la fonction libre `list_client_templates` du module
        (voir sa docstring pour la raison de ce découpage). Conservée comme
        méthode aussi pour que l'API de `FigmaClient` corresponde
        littéralement au regroupement du spec ("Client Figma API")."""
        return await list_client_templates(client_id)


async def list_client_templates(client_id: str) -> list[Template]:
    """Templates du client stockés en PostgreSQL (`ContentTemplate`,
    `figma_file_id`)  ne fait aucun appel à l'API Figma elle-même, c'est
    une lecture de la base de correspondance client -> fichiers.

    Fonction libre, PAS une méthode de `FigmaClient` : son constructeur exige
    `FIGMA_ACCESS_TOKEN` (nécessaire pour les appels API réels), mais cette
    lecture ne l'utilise jamais  en faire une méthode aurait rendu les
    templates d'un client illisibles simplement parce que le token Figma
    n'est pas configuré, alors que les deux opérations sont indépendantes."""
    try:
        from backend.db.repositories.content_repository import ContentTemplateRepository
        from backend.db.session import get_session

        async with get_session() as session:
            rows = await ContentTemplateRepository(session).get_by_client_and_type(UUID(client_id), "visual")
    except Exception as exc:
        logger.warning("figma_client.list_client_templates_failed", client_id=client_id, error=str(exc))
        return []

    templates = [
        Template(
            id=str(r.id),
            client_id=client_id,
            template_type=r.template_type,
            figma_file_id=r.figma_file_id,
            canva_template_id=r.canva_template_id,
            structure=r.structure or {},
        )
        for r in rows
    ]
    logger.info("figma_client.client_templates_listed", client_id=client_id, template_count=len(templates))
    return templates


__all__ = ["FigmaClient", "FigmaFile", "FigmaComponent", "TemplateStructure", "Template", "list_client_templates"]
