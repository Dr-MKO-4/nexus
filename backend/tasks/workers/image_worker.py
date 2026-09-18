"""Worker GPU pour l'Agent Créatif  Prompt 6.1.

"Vérification GPU disponible avant chaque tâche" (spec)  appliqué
uniquement à `train_lora_task` : c'est la SEULE des 3 tâches de ce fichier
qui exécute réellement de l'inférence/entraînement PyTorch EN PROCESS (voir
`tools/creative/lora_trainer.py`). `generate_visual_task`/`upscale_image_task`
délèguent tout le calcul GPU à ComfyUI via HTTP (voir `comfyui_client.py`) 
un check GPU local sur CE worker n'aurait aucun sens pour elles et les
ferait échouer à tort sur un worker sans GPU local mais parfaitement capable
de soumettre des requêtes HTTP à un service ComfyUI distant.
"""

import asyncio

import structlog

from backend.tasks.celery_app import celery_app, default_priority_for_queue
from backend.tasks.queues.redis_queue import QUEUE_IMAGE

logger = structlog.get_logger(__name__)

# Voir llm_worker.py pour la justification complète (inversion business->
# kombu, `Task.apply_async` retombant sur `task_default_priority` sans ce
# `priority=` explicite au niveau du décorateur).
_IMAGE_PRIORITY = default_priority_for_queue(QUEUE_IMAGE)


def _ensure_gpu_available() -> None:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "Aucun GPU CUDA disponible sur ce worker  train_lora_task exige un GPU local "
            "(voir tools/creative/lora_trainer.py: train_lora)."
        )


@celery_app.task(bind=True, name="nexus.image.generate_visual_task", queue=QUEUE_IMAGE, priority=_IMAGE_PRIORITY, max_retries=2)
def generate_visual_task(self, brief: dict, client_id: str, campaign_id: str | None) -> dict:
    """Appelle l'Agent Créatif complet  sérialise le premier
    `visual_assets` produit (`VisualAsset.model_dump(mode="json")`)."""
    from backend.agents.creative.graph import build_creative_graph

    try:
        graph = build_creative_graph()
        initial_state = {
            "client_id": client_id,
            "brief": {**brief, "campaign_id": campaign_id},
            "parsed_brief": None,
            "selected_template": None,
            "style_references": [],
            "ipadapter_inputs": [],
            "controlnet_guidance_path": None,
            "generation_prompt": None,
            "negative_prompt": None,
            "workflow_json": None,
            "prompt_id": None,
            "raw_image_paths": [],
            "quality_evaluation": None,
            "final_image_paths": [],
            "upscaled": False,
            "stored_visual_id": None,
            "visual_assets": [],
        }
        result = asyncio.run(graph.ainvoke(initial_state))
        visual_assets = result.get("visual_assets") or []
        if not visual_assets:
            raise RuntimeError("generate_visual_task : aucun visuel produit par l'Agent Créatif.")
        asset = visual_assets[0]
        payload = asset.model_dump(mode="json") if hasattr(asset, "model_dump") else asset
        logger.info("image_worker.visual_generated", client_id=client_id, campaign_id=campaign_id)
        return payload
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("image_worker.generate_visual_failed", client_id=client_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="nexus.image.train_lora_task", queue=QUEUE_IMAGE, priority=_IMAGE_PRIORITY)
def train_lora_task(client_id: str, image_paths: list[str]) -> str:
    """Entraînement LoRA en background (peut prendre 30-60 min, spec).

    `captions` : absent de la signature imposée par le spec
    (`train_lora_task(client_id, image_paths)`), alors que
    `lora_trainer.prepare_dataset` en exige une par image  repli documenté
    sur une légende générique par image plutôt qu'une légende inventée plus
    "réaliste" mais fausse ; dégrade la qualité de l'entraînement (un LoRA
    apprend mieux avec des légendes descriptives précises par image), limite
    assumée de cette signature de tâche, pas une omission silencieuse."""
    from backend.tools.creative.lora_trainer import export_lora, prepare_dataset, train_lora

    _ensure_gpu_available()

    captions = [f"photo de marque pour le client {client_id}" for _ in image_paths]
    dataset = prepare_dataset(image_paths, captions)
    output_dir = f"data/lora_training/{client_id}"
    lora_path = train_lora("stabilityai/stable-diffusion-xl-base-1.0", dataset, output_dir)
    comfyui_lora_path = export_lora(lora_path, client_id)

    logger.info("image_worker.lora_trained", client_id=client_id, image_count=len(image_paths), comfyui_lora_path=comfyui_lora_path)
    return comfyui_lora_path


@celery_app.task(bind=True, name="nexus.image.upscale_image_task", queue=QUEUE_IMAGE, priority=_IMAGE_PRIORITY, max_retries=2)
def upscale_image_task(self, image_path: str) -> str:
    """Upscale via ComfyUI (Real-ESRGAN, voir comfyui_client.build_upscale_workflow)."""
    from backend.tools.creative.comfyui_client import ComfyUIClient

    async def _run() -> str:
        client = ComfyUIClient()
        try:
            workflow = client.build_upscale_workflow(image_path)
            prompt_id = await client.submit_workflow(workflow)
            output_paths = await client.wait_for_completion(prompt_id, timeout=180)
            if not output_paths:
                raise RuntimeError(f"upscale_image_task : aucune image produite pour {image_path!r}.")
            return output_paths[0]
        finally:
            await client.aclose()

    try:
        upscaled_path = asyncio.run(_run())
        logger.info("image_worker.image_upscaled", image_path=image_path, upscaled_path=upscaled_path)
        return upscaled_path
    except Exception as exc:
        logger.warning("image_worker.upscale_failed", image_path=image_path, error=str(exc))
        raise self.retry(exc=exc, countdown=15)


__all__ = ["generate_visual_task", "train_lora_task", "upscale_image_task"]
