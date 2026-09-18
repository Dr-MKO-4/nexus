"""Modèle PyTorch de scoring de contenu  Prompt 5.3, utilisé par
`evaluate_quality_node` de l'Agent Content en complément du jugement LLM.
"""

import re
from pathlib import Path
from typing import ClassVar

import structlog
import torch
from pydantic import BaseModel, ConfigDict, Field
from torch import nn

logger = structlog.get_logger(__name__)

EMBEDDING_DIM = 768
# 6 features textuelles couvrant les 3 dimensions nommées par le spec
# (longueur, densité mots-clés, lisibilité) + 3 dérivées (longueur de phrase
# moyenne, longueur de mot moyenne, nombre de phrases)  voir
# _compute_text_features. 768 + 6 = 774, conforme à l'entrée Linear(774, 256).
TEXT_FEATURES_DIM = 6
INPUT_DIM = EMBEDDING_DIM + TEXT_FEATURES_DIM

# backend/pytorch_models/scoring/content_scorer.py -> backend/pytorch_models/checkpoints/
# (même convention que ComplexityClassifier.DEFAULT_CHECKPOINT_PATH)
DEFAULT_CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "checkpoints" / "content_scorer.pt"

# Cohérent avec backend.core.memory.embedding_manager.TextEmbedder (768 dim).
_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"


class ContentScore(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

    score_global: float = Field(ge=0, le=1)
    score_seo: float = Field(ge=0, le=1)
    score_readability: float = Field(ge=0, le=1)
    score_engagement: float = Field(ge=0, le=1)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _flesch_reading_ease(text: str, words: list[str], sentences: list[str]) -> float:
    """Approximation de la formule de Flesch, sans dépendance externe
    (`textstat` n'est pas dans requirements/ml.txt) : le compte de syllabes
    est approximé par le nombre de groupes de voyelles par mot  imprécis
    pour le français (digraphes, diacritiques) mais suffisant comme signal
    relatif, dans le même esprit que les heuristiques de fallback documentées
    dans `complexity_classifier._heuristic_predict`."""
    if not words or not sentences:
        return 0.0

    def _count_syllables(word: str) -> int:
        groups = re.findall(r"[aeiouyàâäéèêëïîôöùûü]+", word.lower())
        return max(1, len(groups))

    syllable_count = sum(_count_syllables(w) for w in words)
    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = syllable_count / len(words)
    score = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    return max(0.0, min(100.0, score))


def _compute_text_features(content_text: str, target_keywords: list[str]) -> list[float]:
    """Retourne [longueur, longueur_phrase_moy, longueur_mot_moy,
    densité_mots_clés, lisibilité, nb_phrases], chaque feature normalisée
    entre 0 et 1 pour rester à l'échelle de l'embedding concaténé."""
    words = re.findall(r"\b\w+\b", content_text.lower())
    sentences = _split_sentences(content_text)
    word_count = len(words)

    normalized_length = min(word_count / 1000.0, 1.0)
    avg_sentence_length = min((word_count / len(sentences)) / 40.0, 1.0) if sentences else 0.0
    avg_word_length = min((sum(len(w) for w in words) / word_count) / 12.0, 1.0) if words else 0.0

    # Compte les occurrences de chaque mot-clé (potentiellement multi-mots)
    # comme sous-chaîne du texte brut, pas comme mot isolé de `words` : un
    # `words.count(kw)` raterait systématiquement tout mot-clé à plusieurs
    # mots (ex. "marketing digital" n'apparaît jamais tel quel dans la liste
    # de tokens à un seul mot chacun). Densité = proportion du texte occupée
    # par les occurrences de mots-clés, en nombre de mots.
    lowered_text = content_text.lower()
    keyword_word_count = sum(
        lowered_text.count(kw.lower()) * max(len(kw.split()), 1) for kw in target_keywords
    ) if target_keywords else 0
    keyword_density = min(keyword_word_count / word_count, 1.0) if words else 0.0

    readability = _flesch_reading_ease(content_text, words, sentences) / 100.0
    sentence_count_normalized = min(len(sentences) / 50.0, 1.0)

    return [
        normalized_length,
        avg_sentence_length,
        avg_word_length,
        keyword_density,
        readability,
        sentence_count_normalized,
    ]


class ContentScorer(nn.Module):
    """Architecture (spec Prompt 5.3) : Linear(774,256) -> ReLU -> Dropout ->
    Linear(256,64) -> ReLU -> Linear(64,1) -> Sigmoid."""

    _embedding_model: ClassVar[object | None] = None

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(INPUT_DIM, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )
        # Reste False tant qu'aucun state_dict entraîné n'a été chargé via
        # from_checkpoint() : score_content() retombe alors sur une
        # heuristique dérivée directement des features déterministes.
        self.is_trained = False

    def forward(self, content_embedding: torch.Tensor, text_features: torch.Tensor) -> torch.Tensor:
        x = torch.cat([content_embedding, text_features], dim=-1)
        return self.net(x)

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path | str = DEFAULT_CHECKPOINT_PATH) -> "ContentScorer":
        model = cls()
        path = Path(checkpoint_path)
        if path.exists():
            # weights_only=True : le checkpoint ne contient qu'un state_dict,
            # pas besoin du unpickler complet (voir complexity_classifier.py).
            state_dict = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(state_dict)
            model.is_trained = True
            logger.info("content_scorer.checkpoint_loaded", path=str(path))
        else:
            logger.warning("content_scorer.checkpoint_missing_using_heuristic_score", path=str(path))
        model.eval()
        return model

    @classmethod
    def _get_embedding_model(cls):
        if cls._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("content_scorer.loading_embedding_model", model=_EMBEDDING_MODEL_NAME)
            cls._embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
        return cls._embedding_model

    def score_content(self, content_text: str, target_keywords: list[str]) -> ContentScore:
        text_features = _compute_text_features(content_text, target_keywords)
        length_f, _sentence_len_f, _word_len_f, keyword_density, readability, sentence_count_f = text_features

        if not self.is_trained:
            score_seo = keyword_density
            score_readability = readability
            score_engagement = (length_f + sentence_count_f) / 2
            score_global = (score_seo + score_readability + score_engagement) / 3
            return ContentScore(
                score_global=score_global,
                score_seo=score_seo,
                score_readability=score_readability,
                score_engagement=score_engagement,
            )

        embedding_model = self._get_embedding_model()
        embedding = embedding_model.encode(content_text)

        self.eval()
        with torch.no_grad():
            embedding_tensor = torch.as_tensor(embedding, dtype=torch.float32).unsqueeze(0)
            features_tensor = torch.as_tensor(text_features, dtype=torch.float32).unsqueeze(0)
            score_global = float(self.forward(embedding_tensor, features_tensor).item())

        # Le modèle entraîné ne produit qu'un score global (spec : "Sortie :
        # score 0-1"). Les sous-scores SEO/lisibilité restent dérivés des
        # features déterministes (directement mesurables et interprétables) ;
        # score_engagement est recalibré sur le score global appris.
        return ContentScore(
            score_global=score_global,
            score_seo=keyword_density,
            score_readability=readability,
            score_engagement=score_global,
        )


__all__ = ["ContentScorer", "ContentScore"]
