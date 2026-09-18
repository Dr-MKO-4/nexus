"""Pipeline d'entraînement de ComplexityClassifier sur un jeu de tâches
marketing labellisées (simple/medium/complex).

Format du dataset attendu (JSON) :
    [{"text": "Résume ce rapport en 3 points", "label": "simple"}, ...]
labels valides : "simple", "medium", "complex".
"""

import json
from dataclasses import dataclass
from pathlib import Path

import structlog
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, random_split

from backend.pytorch_models.classifiers.complexity_classifier import (
    DEFAULT_CHECKPOINT_PATH,
    LABELS,
    ComplexityClassifier,
)

logger = structlog.get_logger(__name__)

_LABEL_TO_INDEX = {label: i for i, label in enumerate(LABELS)}


@dataclass
class LabeledTask:
    text: str
    label: str


def load_labeled_dataset(path: Path | str) -> list[LabeledTask]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = [LabeledTask(text=item["text"], label=item["label"]) for item in raw]
    invalid = [t.label for t in tasks if t.label not in _LABEL_TO_INDEX]
    if invalid:
        raise ValueError(f"Labels invalides dans le dataset (attendus {LABELS}) : {sorted(set(invalid))}")
    return tasks


class ComplexityDataset(Dataset):
    """Dataset PyTorch (embedding, label). Accepte soit des `tasks` bruts
    (texte encodé via sentence-transformers), soit des `embeddings`
    déjà calculés + `labels`  ce second chemin évite de dépendre du
    téléchargement d'un modèle d'embedding pour tester la boucle
    d'entraînement elle-même (voir tests)."""

    def __init__(
        self,
        tasks: list[LabeledTask] | None = None,
        *,
        embeddings: torch.Tensor | None = None,
        labels: list[str] | None = None,
    ) -> None:
        if tasks is not None:
            from backend.pytorch_models.classifiers.complexity_classifier import (
                ComplexityClassifier as _CC,
            )

            embedding_model = _CC._get_embedding_model()
            texts = [t.text for t in tasks]
            self._embeddings = torch.as_tensor(embedding_model.encode(texts), dtype=torch.float32)
            self._labels = torch.tensor([_LABEL_TO_INDEX[t.label] for t in tasks], dtype=torch.long)
        elif embeddings is not None and labels is not None:
            self._embeddings = torch.as_tensor(embeddings, dtype=torch.float32)
            self._labels = torch.tensor([_LABEL_TO_INDEX[label] for label in labels], dtype=torch.long)
        else:
            raise ValueError("Fournir soit `tasks`, soit `embeddings`+`labels`.")

    def __len__(self) -> int:
        return len(self._labels)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self._embeddings[idx], self._labels[idx]


@dataclass
class EpochMetrics:
    epoch: int
    train_loss: float
    val_accuracy: float
    val_f1_per_class: dict[str, float]


def _compute_f1_per_class(y_true: list[int], y_pred: list[int]) -> dict[str, float]:
    f1_scores: dict[str, float] = {}
    for idx, label in enumerate(LABELS):
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == idx and p == idx)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != idx and p == idx)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == idx and p != idx)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1_scores[label] = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return f1_scores


def train(
    dataset: Dataset,
    *,
    epochs: int = 20,
    batch_size: int = 16,
    learning_rate: float = 1e-3,
    val_split: float = 0.2,
    checkpoint_path: Path | str = DEFAULT_CHECKPOINT_PATH,
) -> list[EpochMetrics]:
    """Entraîne un ComplexityClassifier sur `dataset`, sauvegarde le meilleur
    modèle (accuracy de validation maximale) à `checkpoint_path`, retourne
    l'historique des métriques par epoch."""
    val_size = max(1, int(len(dataset) * val_split))
    train_size = len(dataset) - val_size
    if train_size <= 0:
        raise ValueError(f"Dataset trop petit ({len(dataset)} exemples) pour un split train/val.")

    train_ds, val_ds = random_split(dataset, [train_size, val_size])
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size)

    model = ComplexityClassifier()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss()

    best_val_accuracy = -1.0
    history: list[EpochMetrics] = []

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for embeddings, labels in train_loader:
            optimizer.zero_grad()
            logits = model(embeddings)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * embeddings.size(0)
        train_loss = total_loss / train_size

        model.eval()
        y_true: list[int] = []
        y_pred: list[int] = []
        with torch.no_grad():
            for embeddings, labels in val_loader:
                logits = model(embeddings)
                preds = torch.argmax(logits, dim=-1)
                y_true.extend(labels.tolist())
                y_pred.extend(preds.tolist())

        val_accuracy = sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(1, len(y_true))
        val_f1 = _compute_f1_per_class(y_true, y_pred)

        metrics = EpochMetrics(
            epoch=epoch, train_loss=train_loss, val_accuracy=val_accuracy, val_f1_per_class=val_f1
        )
        history.append(metrics)
        logger.info(
            "trainer.epoch_completed",
            epoch=epoch,
            train_loss=round(train_loss, 4),
            val_accuracy=round(val_accuracy, 4),
        )

        if val_accuracy > best_val_accuracy:
            best_val_accuracy = val_accuracy
            checkpoint = Path(checkpoint_path)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            model.is_trained = True
            torch.save(model.state_dict(), checkpoint)
            logger.info("trainer.checkpoint_saved", path=str(checkpoint), val_accuracy=round(val_accuracy, 4))

    return history
