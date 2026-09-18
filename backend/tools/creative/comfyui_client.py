"""Client ComfyUI API  Prompt 5.7.

ComfyUI expose une API asynchrone à base de "prompt_id" : `POST /prompt`
soumet un workflow (graphe de nœuds JSON), l'exécution se fait en arrière-plan
côté serveur, et le résultat se récupère via `GET /history/{prompt_id}` une
fois terminé (ou en s'abonnant au WebSocket `/ws`, non utilisé ici  le
polling reste plus simple et suffisant pour un agent qui attend un seul
résultat à la fois).

Real-ESRGAN (post_process, spec Prompt 5.7) : pas de pipeline Python séparé
dans ce projet (aucune dépendance `realesrgan`/`basicsr` dans requirements/
ml.txt  ces paquets ont des chaînes de dépendances fragiles et dupliqueraient
un moteur d'inférence GPU que ComfyUI héberge déjà). L'upscale est donc
soumis à ComfyUI lui-même comme un second workflow
(`build_upscale_workflow`, nœuds `UpscaleModelLoader`+`ImageUpscaleWithModel`,
standards dans une installation ComfyUI avec le modèle Real-ESRGAN
téléchargé)  cohérent avec le choix déjà fait pour l'embedding CLIP/texte
(un seul service GPU, `pytorch_models`/ComfyUI, jamais dupliqué dans le
process agent).

Limite honnête sur `get_status`/`get_output_images` : la forme exacte du
JSON retourné par `GET /history/{prompt_id}` (clés `status.status_str`,
`status.completed`, `status.messages`, `outputs.*.images`) est basée sur le
format documenté/communément observé de l'API ComfyUI, PAS vérifiée contre
un serveur ComfyUI réel dans ce sandbox (aucune instance disponible) 
contrairement aux autres clients de ce projet (Google Ads, Mautic...), dont
les écarts avaient pu être confirmés par erreur HTTP réelle. À revérifier
contre une vraie instance avant mise en production.
"""

import asyncio

import structlog
import httpx
from pydantic import BaseModel, ConfigDict

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_UPSCALE_MODEL = "RealESRGAN_x4plus.pth"


class ComfyUIStatus(BaseModel):
    model_config = _STRICT_CONFIG

    prompt_id: str
    status: str  # "pending" | "running" | "completed" | "error"
    completed: bool
    error: str | None = None


class ComfyUIClient:
    def __init__(self, timeout: float = 60.0) -> None:
        self._client = httpx.AsyncClient(base_url=settings.COMFYUI_BASE_URL, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def submit_workflow(self, workflow_json: dict) -> str:
        response = await self._client.post("/prompt", json={"prompt": workflow_json})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]
        logger.info("comfyui_client.workflow_submitted", prompt_id=prompt_id)
        return prompt_id

    async def get_status(self, prompt_id: str) -> ComfyUIStatus:
        response = await self._client.get(f"/history/{prompt_id}")
        response.raise_for_status()
        history = response.json()

        entry = history.get(prompt_id)
        if entry is None:
            # Le prompt_id n'apparaît dans /history qu'une fois son
            # exécution démarrée côté serveur (file d'attente ComfyUI) 
            # absent = toujours en attente, pas une erreur.
            return ComfyUIStatus(prompt_id=prompt_id, status="pending", completed=False)

        status_info = entry.get("status", {})
        if status_info.get("status_str") == "error":
            # Toujours remonter l'erreur ici, même sans message
            # "execution_error" détaillé (ex: format de message différent
            # selon la version de ComfyUI)  un `status_str == "error"` sans
            # message correspondant ne doit JAMAIS retomber silencieusement
            # sur le chemin "completed" ci-dessous (c'était le bug : `or`
            # moins prioritaire que `and` faisait ignorer l'erreur si
            # `error_messages` était vide).
            error_messages = [m for m in status_info.get("messages", []) if m[0] == "execution_error"]
            error_detail = str(error_messages[0]) if error_messages else "ComfyUI a signalé une erreur sans détail exploitable dans /history."
            return ComfyUIStatus(prompt_id=prompt_id, status="error", completed=True, error=error_detail)

        completed = bool(status_info.get("completed", False))
        return ComfyUIStatus(
            prompt_id=prompt_id, status="completed" if completed else "running", completed=completed
        )

    async def get_output_images(self, prompt_id: str) -> list[str]:
        response = await self._client.get(f"/history/{prompt_id}")
        response.raise_for_status()
        history = response.json()
        entry = history.get(prompt_id, {})

        image_paths: list[str] = []
        for node_output in entry.get("outputs", {}).values():
            for image in node_output.get("images", []):
                subfolder = image.get("subfolder", "")
                filename = image["filename"]
                path = f"{subfolder}/{filename}" if subfolder else filename
                image_paths.append(path)

        logger.info("comfyui_client.output_images_fetched", prompt_id=prompt_id, image_count=len(image_paths))
        return image_paths

    async def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> list[str]:
        elapsed = 0.0
        while elapsed < timeout:
            status = await self.get_status(prompt_id)
            if status.status == "error":
                raise RuntimeError(f"ComfyUI workflow {prompt_id} a échoué : {status.error}")
            if status.completed:
                return await self.get_output_images(prompt_id)
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

        raise TimeoutError(f"ComfyUI workflow {prompt_id} n'a pas terminé après {timeout}s.")

    def build_flux_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        style_reference_paths: list[str],
        controlnet_image_path: str | None,
    ) -> dict:
        """Workflow Flux (checkpoint `flux1-dev.safetensors`) avec IPAdapter
        pour les références de style et, optionnellement, un ControlNet pour
        respecter la structure du template (spec : `template_structure` via
        `style_transfer.build_controlnet_guidance`)."""
        nodes: dict = {
            "checkpoint_loader": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "flux1-dev.safetensors"},
            },
            "positive_prompt": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt, "clip": ["checkpoint_loader", 1]},
            },
            "negative_prompt": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative_prompt, "clip": ["checkpoint_loader", 1]},
            },
            "empty_latent": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
        }

        model_ref = ["checkpoint_loader", 0]
        if style_reference_paths:
            nodes["ipadapter_loader"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter_flux.safetensors"}}
            nodes["ipadapter_images"] = {
                "class_type": "LoadImageBatch",
                "inputs": {"image_paths": style_reference_paths},
            }
            nodes["ipadapter_apply"] = {
                "class_type": "IPAdapterApply",
                "inputs": {
                    "model": model_ref,
                    "ipadapter": ["ipadapter_loader", 0],
                    "image": ["ipadapter_images", 0],
                    "weight": 0.8,
                },
            }
            model_ref = ["ipadapter_apply", 0]

        if controlnet_image_path:
            nodes["controlnet_loader"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "flux-controlnet-canny.safetensors"}}
            nodes["controlnet_image"] = {"class_type": "LoadImage", "inputs": {"image": controlnet_image_path}}
            nodes["controlnet_apply"] = {
                "class_type": "ControlNetApply",
                "inputs": {
                    "conditioning": ["positive_prompt", 0],
                    "control_net": ["controlnet_loader", 0],
                    "image": ["controlnet_image", 0],
                    "strength": 0.7,
                },
            }
            positive_conditioning = ["controlnet_apply", 0]
        else:
            positive_conditioning = ["positive_prompt", 0]

        nodes["sampler"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": model_ref,
                "positive": positive_conditioning,
                "negative": ["negative_prompt", 0],
                "latent_image": ["empty_latent", 0],
                "seed": 0,
                "steps": 25,
                "cfg": 3.5,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        }
        nodes["vae_decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["sampler", 0], "vae": ["checkpoint_loader", 2]}}
        nodes["save_image"] = {"class_type": "SaveImage", "inputs": {"images": ["vae_decode", 0], "filename_prefix": "nexus_creative"}}

        return nodes

    def build_lora_workflow(self, prompt: str, lora_name: str, strength: float) -> dict:
        """Workflow Flux + un LoRA client (entraîné par lora_trainer.py,
        exporté dans le dossier ComfyUI models/loras  voir export_lora)."""
        return {
            "checkpoint_loader": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev.safetensors"}},
            "lora_loader": {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": ["checkpoint_loader", 0],
                    "clip": ["checkpoint_loader", 1],
                    "lora_name": lora_name,
                    "strength_model": strength,
                    "strength_clip": strength,
                },
            },
            "positive_prompt": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["lora_loader", 1]}},
            "negative_prompt": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["lora_loader", 1]}},
            "empty_latent": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
            "sampler": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["lora_loader", 0],
                    "positive": ["positive_prompt", 0],
                    "negative": ["negative_prompt", 0],
                    "latent_image": ["empty_latent", 0],
                    "seed": 0,
                    "steps": 25,
                    "cfg": 3.5,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": 1.0,
                },
            },
            "vae_decode": {"class_type": "VAEDecode", "inputs": {"samples": ["sampler", 0], "vae": ["checkpoint_loader", 2]}},
            "save_image": {"class_type": "SaveImage", "inputs": {"images": ["vae_decode", 0], "filename_prefix": "nexus_creative_lora"}},
        }

    def build_upscale_workflow(self, image_path: str, model_name: str = _DEFAULT_UPSCALE_MODEL) -> dict:
        """Workflow d'upscale Real-ESRGAN  voir docstring de module pour le
        choix de le déléguer à ComfyUI plutôt qu'à un pipeline Python local."""
        return {
            "load_image": {"class_type": "LoadImage", "inputs": {"image": image_path}},
            "upscale_model_loader": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": model_name}},
            "upscale": {
                "class_type": "ImageUpscaleWithModel",
                "inputs": {"upscale_model": ["upscale_model_loader", 0], "image": ["load_image", 0]},
            },
            "save_image": {"class_type": "SaveImage", "inputs": {"images": ["upscale", 0], "filename_prefix": "nexus_upscaled"}},
        }


__all__ = ["ComfyUIClient", "ComfyUIStatus"]
