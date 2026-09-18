"""Classifieur de sentiment PyTorch multilingue  Prompt 5.4, utilisé par
`sentiment_analysis_node`/`crisis_detector_node` de l'Agent Social.
"""

import re
from pathlib import Path
from typing import ClassVar, Literal

import structlog
import torch
from pydantic import BaseModel, ConfigDict, Field
from torch import nn

logger = structlog.get_logger(__name__)

SentimentLabel = Literal["positif", "neutre", "négatif"]
LABELS: tuple[SentimentLabel, ...] = ("positif", "neutre", "négatif")
ENCODER_DIM = 768
_ENCODER_MODEL_NAME = "distilbert-base-multilingual-cased"

# backend/pytorch_models/classifiers/sentiment_classifier.py -> backend/pytorch_models/checkpoints/
DEFAULT_CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "checkpoints" / "sentiment_classifier.pt"

# Un signal "négatif à haute confiance" est un signal de crise potentielle au
# niveau d'un texte individuel ; `detect_crisis_signal` agrège ce signal sur
# un lot de textes (voir sa docstring).
_CRISIS_CONFIDENCE_THRESHOLD = 0.7

# Heuristiques de fallback (français + anglais, léger)  actives tant
# qu'aucun checkpoint entraîné n'est chargé, même principe que
# ComplexityClassifier._heuristic_predict.
_NEGATIVE_WORDS = (
    "nul", "mauvais", "horrible", "scandale", "arnaque", "déçu", "décevant", "inadmissible",
    "honteux", "catastrophe", "boycott", "jamais plus", "pire", "colère", "furieux",
)
_POSITIVE_WORDS = (
    "excellent", "génial", "parfait", "super", "top", "recommande", "adore", "merci",
    "bravo", "satisfait", "content", "impeccable",
)


def _heuristic_predict(text: str) -> tuple[SentimentLabel, float]:
    lowered = text.lower()
    negative_hits = sum(1 for w in _NEGATIVE_WORDS if w in lowered)
    positive_hits = sum(1 for w in _POSITIVE_WORDS if w in lowered)

    if negative_hits == 0 and positive_hits == 0:
        return "neutre", 0.5
    if negative_hits > positive_hits:
        confidence = min(0.5 + 0.15 * negative_hits, 0.95)
        return "négatif", confidence
    if positive_hits > negative_hits:
        confidence = min(0.5 + 0.15 * positive_hits, 0.95)
        return "positif", confidence
    return "neutre", 0.5


class SentimentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

    label: SentimentLabel
    confidence: float = Field(ge=0, le=1)
    is_crisis_signal: bool


class SentimentClassifier(nn.Module):
    """Tête de classification : Linear(768, 3) -> [positif, neutre, négatif]
    (spec Prompt 5.4), au-dessus d'un encodeur distilbert-base-multilingual-
    cased. L'encodeur n'est chargé que lorsqu'un checkpoint entraîné existe
    (voir `from_checkpoint`)  comme pour ComplexityClassifier, tant
    qu'aucune tête entraînée n'est disponible, `analyze_sentiment` retombe
    sur une heuristique lexicale plutôt que de faire tourner un classifieur
    non entraîné (poids aléatoires) sur un encodeur pré-entraîné mais
    fine-tuné pour rien."""

    # Nuance vis-à-vis du spec ("Encoder... fine-tuné pour le marketing") :
    # seule la tête `self.classifier` (Linear) est un `nn.Module` de cette
    # classe, donc seule elle peut être sauvegardée/chargée via
    # from_checkpoint(). L'encodeur distilbert (_get_encoder) reste figé sur
    # ses poids pré-entraînés HuggingFace  c'est un classifieur "linear
    # probe" au-dessus d'un encodeur gelé, pas un fine-tuning de bout en bout
    # de l'encodeur lui-même. Un vrai fine-tuning de l'encodeur nécessiterait
    # de l'inclure dans ce nn.Module et un pipeline d'entraînement dédié
    # (voir classifiers/trainer.py pour le pattern équivalent utilisé par
    # ComplexityClassifier)  non fait ici, pas d'omission silencieuse.
    _encoder: ClassVar[object | None] = None
    _tokenizer: ClassVar[object | None] = None

    def __init__(self) -> None:
        super().__init__()
        self.classifier = nn.Linear(ENCODER_DIM, len(LABELS))
        self.is_trained = False

    def forward(self, pooled_embedding: torch.Tensor) -> torch.Tensor:
        return self.classifier(pooled_embedding)

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path | str = DEFAULT_CHECKPOINT_PATH) -> "SentimentClassifier":
        model = cls()
        path = Path(checkpoint_path)
        if path.exists():
            state_dict = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(state_dict)
            model.is_trained = True
            logger.info("sentiment_classifier.checkpoint_loaded", path=str(path))
        else:
            logger.warning("sentiment_classifier.checkpoint_missing_using_heuristics", path=str(path))
        model.eval()
        return model

    @classmethod
    def _get_encoder(cls):
        if cls._encoder is None:
            from transformers import AutoModel, AutoTokenizer

            logger.info("sentiment_classifier.loading_encoder", model=_ENCODER_MODEL_NAME)
            cls._tokenizer = AutoTokenizer.from_pretrained(_ENCODER_MODEL_NAME)
            cls._encoder = AutoModel.from_pretrained(_ENCODER_MODEL_NAME)
            cls._encoder.eval()
        return cls._tokenizer, cls._encoder

    def _encode(self, text: str) -> torch.Tensor:
        tokenizer, encoder = self._get_encoder()
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            outputs = encoder(**inputs)
        # Pooling par le token [CLS] (première position)  convention standard
        # pour les encodeurs de la famille BERT/DistilBERT en classification.
        return outputs.last_hidden_state[:, 0, :]

    def analyze_sentiment(self, text: str) -> SentimentResult:
        if not text or not text.strip():
            return SentimentResult(label="neutre", confidence=0.5, is_crisis_signal=False)

        if not self.is_trained:
            label, confidence = _heuristic_predict(text)
        else:
            self.eval()
            with torch.no_grad():
                pooled = self._encode(text)
                logits = self.forward(pooled)
                probabilities = torch.softmax(logits, dim=-1).squeeze(0)
                predicted_index = int(torch.argmax(probabilities).item())
                label = LABELS[predicted_index]
                confidence = float(probabilities[predicted_index].item())

        is_crisis_signal = label == "négatif" and confidence >= _CRISIS_CONFIDENCE_THRESHOLD
        return SentimentResult(label=label, confidence=confidence, is_crisis_signal=is_crisis_signal)

    def analyze_batch(self, texts: list[str]) -> list[SentimentResult]:
        return [self.analyze_sentiment(text) for text in texts]

    def detect_crisis_signal(self, texts: list[str], threshold: float = 0.7) -> bool:
        """Signal de crise au niveau du lot : au moins `threshold` (fraction,
        0-1) des textes sont individuellement des `is_crisis_signal`  une
        poignée de commentaires négatifs isolés n'est pas une crise, une
        proportion significative du volume l'est."""
        if not texts:
            return False
        results = self.analyze_batch(texts)
        crisis_ratio = sum(1 for r in results if r.is_crisis_signal) / len(results)
        return crisis_ratio >= threshold


__all__ = ["SentimentClassifier", "SentimentResult", "SentimentLabel", "LABELS"]
