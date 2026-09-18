"""Classifieur PyTorch de complexité de tâche (simple/medium/complex), utilisé
par HybridRouter (backend/llm/router/hybrid_router.py) pour choisir un modèle
LLM proportionné à la difficulté réelle de chaque tâche.
"""

from pathlib import Path
from typing import ClassVar, Literal

import structlog
import torch
from torch import nn

logger = structlog.get_logger(__name__)

ComplexityLabel = Literal["simple", "medium", "complex"]
LABELS: tuple[ComplexityLabel, ...] = ("simple", "medium", "complex")
EMBEDDING_DIM = 768

# backend/pytorch_models/classifiers/complexity_classifier.py -> backend/pytorch_models/checkpoints/
DEFAULT_CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "checkpoints" / "complexity_classifier.pt"

# Cohérent avec backend.core.memory.embedding_manager.TextEmbedder (Prompt 2.3) :
# même modèle, pour que l'espace vectoriel appris par ce classifieur corresponde
# à celui réellement produit en amont.
_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

# Heuristiques de fallback (aucune dépendance PyTorch/embeddings)  actives
# tant qu'aucun checkpoint entraîné n'est chargé.
_SIMPLE_KEYWORDS = ("classifie", "classification", "extrait", "extraction", "catégorise", "identifie")
_COMPLEX_KEYWORDS = ("génère", "rédige", "raisonne", "raisonnement", "analyse approfondie", "planifie", "stratégie")


def _heuristic_predict(task_description: str) -> ComplexityLabel:
    """complex : > 200 tokens, OU mot-clé de génération longue/raisonnement
    (signal fort, suffit seul quel que soit la longueur).
    simple : < 50 tokens ET mot-clé de classification/extraction  la seule
    brièveté ne suffit PAS : une instruction courte sans marqueur de tâche
    légère ("Résume cette réunion") est un signal ambigu, pas "simple" par
    défaut (sinon "medium" ne serait quasiment jamais atteint en pratique,
    la plupart des instructions d'agent étant courtes).
    medium : tout le reste, y compris les textes courts sans mot-clé."""
    token_count = len(task_description.split())
    lowered = task_description.lower()

    if token_count > 200 or any(k in lowered for k in _COMPLEX_KEYWORDS):
        return "complex"
    if token_count < 50 and any(k in lowered for k in _SIMPLE_KEYWORDS):
        return "simple"
    return "medium"


class ComplexityClassifier(nn.Module):
    """Architecture : Linear(768,256)+ReLU+Dropout(.3) -> Linear(256,64)+ReLU+
    Dropout(.2) -> Linear(64,3). `predict()` ne prend que le texte brut en
    entrée (embedding calculé en interne, via sentence-transformers) : c'est
    ce service (pytorch_models) qui héberge la stack ML, il n'a pas besoin de
    passer par sa propre API HTTP pour obtenir un embedding de lui-même."""

    _embedding_model: ClassVar[object | None] = None

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(EMBEDDING_DIM, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, len(LABELS)),
        )
        # Reste False tant qu'aucun state_dict entraîné n'a été chargé via
        # from_checkpoint() : predict() retombe alors sur les heuristiques.
        self.is_trained = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path | str = DEFAULT_CHECKPOINT_PATH) -> "ComplexityClassifier":
        """Charge un modèle entraîné depuis un fichier .pt (state_dict). Si le
        fichier n'existe pas (modèle jamais entraîné), retourne un modèle non
        entraîné  `predict()` utilisera alors systématiquement les
        heuristiques de fallback plutôt que d'échouer."""
        model = cls()
        path = Path(checkpoint_path)
        if path.exists():
            # weights_only=True : le checkpoint ne contient qu'un state_dict
            # (tenseurs), pas besoin du unpickler complet - évite l'exécution
            # de code arbitraire si le fichier venait à être corrompu/remplacé.
            state_dict = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(state_dict)
            model.is_trained = True
            logger.info("complexity_classifier.checkpoint_loaded", path=str(path))
        else:
            logger.warning("complexity_classifier.checkpoint_missing_using_heuristics", path=str(path))
        model.eval()
        return model

    @classmethod
    def _get_embedding_model(cls):
        if cls._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("complexity_classifier.loading_embedding_model", model=_EMBEDDING_MODEL_NAME)
            cls._embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
        return cls._embedding_model

    def predict(self, task_description: str) -> ComplexityLabel:
        if not self.is_trained:
            return _heuristic_predict(task_description)

        embedding_model = self._get_embedding_model()
        embedding = embedding_model.encode(task_description)
        return self.predict_from_embedding(embedding)

    def predict_from_embedding(self, embedding) -> ComplexityLabel:
        """Variante de `predict()` prenant un embedding déjà calculé (768 dim)
        plutôt que du texte brut  évite de recalculer l'embedding quand
        l'appelant (ex. router_service.py) l'a déjà sous la main, et permet de
        tester la tête de classification indépendamment du modèle
        d'embedding."""
        self.eval()
        with torch.no_grad():
            tensor = torch.as_tensor(embedding, dtype=torch.float32).unsqueeze(0)
            logits = self.forward(tensor)
            predicted_index = int(torch.argmax(logits, dim=-1).item())
        return LABELS[predicted_index]
