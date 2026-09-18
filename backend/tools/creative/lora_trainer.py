"""Entraîneur LoRA (PEFT + Diffusers, SDXL)  Prompt 5.7.

Ce module appartient au service `pytorch_models` (le seul à installer
`requirements/ml.txt` : torch, diffusers, peft  voir Dockerfile.ml), pas au
backend général, même limite déjà documentée pour les autres modèles PyTorch
du projet (ContentScorer, AnomalyDetector, SentimentClassifier).

Honnêteté sur la testabilité (pas une omission silencieuse) : `train_lora`/
`evaluate_lora` nécessitent un GPU CUDA et le téléchargement du checkpoint de
base SDXL (~7 Go)  non exécutables dans un environnement de développement
sans GPU. `prepare_dataset` (aucune dépendance GPU) et `export_lora` (simple
copie de fichier) sont, eux, entièrement testables sans GPU et le sont
réellement (voir tests). Le code d'entraînement suit le script de référence
HuggingFace `diffusers/examples/text_to_image/train_text_to_image_lora_sdxl.py`
(schéma d'entraînement standard : bruit gaussien + prédiction du bruit par
l'UNet + MSE), adapté ici en fonctions réutilisables plutôt qu'un script CLI.
"""

import shutil
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict, Field

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)
_SDXL_RESOLUTION = 1024


class LoRAEvalResult(BaseModel):
    model_config = _STRICT_CONFIG

    lora_path: str
    test_prompts: list[str]
    clip_scores: list[float] = Field(description="Score CLIP (similarité image générée / prompt) par prompt de test.")
    average_clip_score: float


def prepare_dataset(image_paths: list[str], captions: list[str]):
    """Construit un `datasets.Dataset` (image, caption) prêt pour
    l'entraînement LoRA SDXL  redimensionnement à 1024x1024 (résolution
    native SDXL), aucune dépendance GPU."""
    if len(image_paths) != len(captions):
        raise ValueError(f"image_paths ({len(image_paths)}) et captions ({len(captions)}) doivent avoir la même longueur.")
    if not image_paths:
        raise ValueError("image_paths ne peut pas être vide.")

    from datasets import Dataset
    from PIL import Image

    def _load_and_resize(path: str) -> Image.Image:
        image = Image.open(path).convert("RGB")
        return image.resize((_SDXL_RESOLUTION, _SDXL_RESOLUTION))

    records = [{"image": _load_and_resize(path), "caption": caption} for path, caption in zip(image_paths, captions)]
    dataset = Dataset.from_list(records)
    logger.info("lora_trainer.dataset_prepared", sample_count=len(dataset))
    return dataset


def train_lora(
    base_model: str,
    dataset,
    output_dir: str,
    rank: int = 4,
    alpha: int = 8,
    epochs: int = 100,
) -> str:
    """Entraîne un LoRA sur `base_model` (checkpoint SDXL HuggingFace, ex.
    "stabilityai/stable-diffusion-xl-base-1.0") via PEFT + Diffusers.
    Nécessite un GPU CUDA  non exécuté dans ce sandbox (voir docstring de
    module)."""
    import torch
    from diffusers import StableDiffusionXLPipeline
    from peft import LoraConfig
    from torch.utils.data import DataLoader

    if not torch.cuda.is_available():
        raise RuntimeError(
            "train_lora nécessite un GPU CUDA (entraînement SDXL). "
            "Aucun GPU détecté dans ce process  à exécuter sur le worker GPU dédié "
            "(voir Prompt 6.1, tasks/workers/image_worker.py: train_lora_task)."
        )

    pipeline = StableDiffusionXLPipeline.from_pretrained(base_model, torch_dtype=torch.float16).to("cuda")
    lora_config = LoraConfig(
        r=rank,
        lora_alpha=alpha,
        target_modules=["to_k", "to_q", "to_v", "to_out.0"],
        init_lora_weights="gaussian",
    )
    pipeline.unet.add_adapter(lora_config)

    trainable_params = [p for p in pipeline.unet.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=1e-4)

    def _collate(batch: list[dict]) -> dict:
        pixel_values = torch.stack(
            [torch.from_numpy((__import__("numpy").array(item["image"]) / 127.5 - 1.0).astype("float32")).permute(2, 0, 1) for item in batch]
        )
        captions = [item["caption"] for item in batch]
        return {"pixel_values": pixel_values, "captions": captions}

    dataloader = DataLoader(dataset, batch_size=1, shuffle=True, collate_fn=_collate)
    noise_scheduler = pipeline.scheduler

    pipeline.unet.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        for batch in dataloader:
            pixel_values = batch["pixel_values"].to("cuda", dtype=torch.float16)
            latents = pipeline.vae.encode(pixel_values).latent_dist.sample() * pipeline.vae.config.scaling_factor

            noise = torch.randn_like(latents)
            timesteps = torch.randint(0, noise_scheduler.config.num_train_timesteps, (latents.shape[0],), device="cuda")
            noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)

            prompt_embeds, pooled_prompt_embeds = pipeline.encode_prompt(batch["captions"], device="cuda")[:2]
            added_cond_kwargs = {"text_embeds": pooled_prompt_embeds, "time_ids": torch.zeros(latents.shape[0], 6, device="cuda")}

            noise_pred = pipeline.unet(
                noisy_latents, timesteps, encoder_hidden_states=prompt_embeds, added_cond_kwargs=added_cond_kwargs
            ).sample

            loss = torch.nn.functional.mse_loss(noise_pred, noise)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        logger.info("lora_trainer.training_epoch", epoch=epoch, loss=epoch_loss / max(len(dataloader), 1))

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    pipeline.unet.save_attn_procs(output_path)

    logger.info("lora_trainer.training_completed", output_dir=output_dir, epochs=epochs, rank=rank, alpha=alpha)
    return str(output_path)


def evaluate_lora(lora_path: str, test_prompts: list[str]) -> LoRAEvalResult:
    """Génère une image par prompt de test avec le LoRA chargé, score chaque
    résultat par similarité CLIP au prompt. Nécessite un GPU CUDA (voir
    docstring de module)."""
    import torch
    from diffusers import StableDiffusionXLPipeline

    if not torch.cuda.is_available():
        raise RuntimeError("evaluate_lora nécessite un GPU CUDA  voir docstring de module.")

    pipeline = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16
    ).to("cuda")
    pipeline.unet.load_attn_procs(lora_path)

    from transformers import CLIPModel, CLIPProcessor

    clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cuda")
    clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    clip_scores: list[float] = []
    for prompt in test_prompts:
        image = pipeline(prompt, num_inference_steps=25).images[0]
        inputs = clip_processor(text=[prompt], images=image, return_tensors="pt", padding=True).to("cuda")
        outputs = clip_model(**inputs)
        score = torch.nn.functional.cosine_similarity(outputs.image_embeds, outputs.text_embeds).item()
        clip_scores.append(score)

    average = sum(clip_scores) / len(clip_scores) if clip_scores else 0.0
    logger.info("lora_trainer.evaluation_completed", lora_path=lora_path, average_clip_score=average)
    return LoRAEvalResult(lora_path=lora_path, test_prompts=test_prompts, clip_scores=clip_scores, average_clip_score=average)


def export_lora(lora_path: str, client_id: str) -> str:
    """Copie le LoRA entraîné dans le dossier `models/loras` de ComfyUI
    (`settings.COMFYUI_LORA_DIR`, volume partagé  voir settings.py). Aucune
    dépendance GPU : pure opération fichier, testable directement."""
    source = Path(lora_path)
    if not source.exists():
        raise FileNotFoundError(f"lora_path introuvable : {lora_path!r}")

    destination_dir = Path(settings.COMFYUI_LORA_DIR)
    destination_dir.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        destination = destination_dir / f"{client_id}_{source.name}"
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination = destination_dir / f"{client_id}_{source.name}"
        shutil.copy2(source, destination)

    logger.info("lora_trainer.lora_exported", client_id=client_id, source=str(source), destination=str(destination))
    # Retourne le NOM (relatif à COMFYUI_LORA_DIR), pas le chemin absolu :
    # c'est ce que `comfyui_client.build_lora_workflow`'s `lora_name`
    # attend (un nœud LoraLoader de ComfyUI référence un LoRA par son nom de
    # fichier relatif à son propre dossier `models/loras`, jamais par un
    # chemin absolu du système de fichiers de l'appelant)  sans ça,
    # "comfyui_lora_path" serait inutilisable tel quel par
    # build_lora_workflow, obligeant l'appelant à refaire lui-même
    # `Path(...).name`.
    return destination.name


__all__ = ["LoRAEvalResult", "prepare_dataset", "train_lora", "evaluate_lora", "export_lora"]
