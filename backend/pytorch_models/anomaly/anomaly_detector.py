"""Détecteur d'anomalies PyTorch (autoencoder)  Prompt 5.6, utilisé par
`detect_anomalies_pytorch_node` de l'Agent Analytics (et par
`backend.core.graph.measure_cluster.detect_anomalies_pytorch_node`, qui
construit `AnomalyDetector()` sans argument  voir `__init__`).
"""

from pathlib import Path

import structlog
import torch
from pydantic import BaseModel, ConfigDict
from torch import nn

logger = structlog.get_logger(__name__)

_STRICT_CONFIG = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True)

# backend/pytorch_models/anomaly/anomaly_detector.py -> backend/pytorch_models/checkpoints/
DEFAULT_CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "checkpoints" / "anomaly_detector.pt"

# Nombre de KPIs attendu par défaut (cac, ltv, roas, cpa, email_roi,
# organic_traffic_growth, nb_visits, nb_conversions  les 8 métriques
# produites par kpi_calculator.py) : un choix documenté puisque
# `measure_cluster.detect_anomalies_pytorch_node` construit `AnomalyDetector()`
# sans argument, donc sans connaître à l'avance la taille réelle des vecteurs
# de KPIs qui lui seront soumis. `fit()` et `detect()` re-dimensionnent les
# couches si la donnée réelle a une taille différente (voir leurs docstrings).
DEFAULT_N_FEATURES = 8
_TRAIN_EPOCHS = 100
_LEARNING_RATE = 1e-3
_ANOMALY_PERCENTILE = 95


class AnomalyResult(BaseModel):
    model_config = _STRICT_CONFIG

    is_anomaly: bool
    score: float
    explanation: str


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(int(len(sorted_values) * percentile / 100), len(sorted_values) - 1)
    return sorted_values[index]


def _pad_or_truncate(vector: list[float], n_features: int) -> list[float]:
    if len(vector) == n_features:
        return list(vector)
    if len(vector) > n_features:
        return list(vector[:n_features])
    return list(vector) + [0.0] * (n_features - len(vector))


class AnomalyDetector(nn.Module):
    """Architecture (spec Prompt 5.6) :
    Encoder Linear(n_features,64) -> ReLU -> Linear(64,16) -> ReLU
    Decoder Linear(16,64) -> ReLU -> Linear(64,n_features)
    Détection par erreur de reconstruction (MSE), seuil = percentile 95 des
    scores d'entraînement (`fit()`)."""

    def __init__(self, n_features: int = DEFAULT_N_FEATURES) -> None:
        super().__init__()
        self.n_features = n_features
        self._build_layers(n_features)
        self.is_trained = False
        self._threshold: float | None = None

    def _build_layers(self, n_features: int) -> None:
        self.encoder = nn.Sequential(nn.Linear(n_features, 64), nn.ReLU(), nn.Linear(64, 16), nn.ReLU())
        self.decoder = nn.Sequential(nn.Linear(16, 64), nn.ReLU(), nn.Linear(64, n_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))

    def compute_anomaly_score(self, x: torch.Tensor) -> float:
        self.eval()
        with torch.no_grad():
            reconstruction = self.forward(x)
            mse = torch.mean((x - reconstruction) ** 2).item()
        return float(mse)

    def detect(self, metrics_vector: list[float], threshold: float | None = None) -> AnomalyResult:
        """`threshold` explicite prioritaire ; sinon le seuil appris par
        `fit()` ; si ni l'un ni l'autre n'est disponible (détecteur jamais
        entraîné), repli neutre  un autoencoder à poids aléatoires produirait
        un score de reconstruction sans aucune signification calibrée, le
        signaler comme "anomalie" serait un faux signal, pas une détection."""
        active_threshold = threshold if threshold is not None else self._threshold
        if active_threshold is None:
            logger.warning("anomaly_detector.no_threshold_available_neutral_fallback")
            return AnomalyResult(
                is_anomaly=False, score=0.0, explanation="Détecteur non entraîné (fit() jamais appelé)  repli neutre, aucune anomalie signalée."
            )

        padded = _pad_or_truncate(metrics_vector, self.n_features)
        tensor = torch.as_tensor(padded, dtype=torch.float32).unsqueeze(0)
        score = self.compute_anomaly_score(tensor)
        is_anomaly = score > active_threshold
        explanation = (
            f"Score de reconstruction {score:.4f} "
            f"{'supérieur' if is_anomaly else 'inférieur ou égal'} au seuil {active_threshold:.4f} "
            f"(percentile {_ANOMALY_PERCENTILE} de l'historique d'entraînement)."
        )
        return AnomalyResult(is_anomaly=is_anomaly, score=score, explanation=explanation)

    def fit(self, historical_data: list[list[float]]) -> None:
        """Entraîne l'autoencoder sur l'historique de vecteurs de KPIs
        (reconstruction non supervisée), fixe le seuil au percentile 95 des
        scores obtenus sur ce même historique. Si `historical_data` a une
        taille de vecteur différente de `self.n_features` (fixée à la
        construction, potentiellement un défaut arbitraire  voir
        DEFAULT_N_FEATURES), les couches sont reconstruites pour correspondre
        à la donnée réelle : `n_features` n'est vraiment connu qu'au moment de
        l'entraînement, pas avant."""
        if not historical_data:
            raise ValueError("historical_data ne peut pas être vide.")

        actual_n_features = len(historical_data[0])
        if actual_n_features != self.n_features:
            logger.info("anomaly_detector.resizing_layers", old=self.n_features, new=actual_n_features)
            self.n_features = actual_n_features
            self._build_layers(actual_n_features)

        data = torch.as_tensor(historical_data, dtype=torch.float32)
        optimizer = torch.optim.Adam(self.parameters(), lr=_LEARNING_RATE)
        criterion = nn.MSELoss()

        self.train()
        for epoch in range(_TRAIN_EPOCHS):
            optimizer.zero_grad()
            reconstruction = self.forward(data)
            loss = criterion(reconstruction, data)
            loss.backward()
            optimizer.step()
            if epoch % 20 == 0 or epoch == _TRAIN_EPOCHS - 1:
                logger.debug("anomaly_detector.training_epoch", epoch=epoch, loss=loss.item())

        self.eval()
        with torch.no_grad():
            per_sample_scores = [
                float(torch.mean((data[i] - self.forward(data[i : i + 1]).squeeze(0)) ** 2).item())
                for i in range(data.shape[0])
            ]
        self._threshold = _percentile(per_sample_scores, _ANOMALY_PERCENTILE)
        self.is_trained = True
        logger.info("anomaly_detector.fitted", sample_count=len(historical_data), threshold=self._threshold)

        self._save_checkpoint()

    def _save_checkpoint(self, checkpoint_path: Path | str = DEFAULT_CHECKPOINT_PATH) -> None:
        path = Path(checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Contrairement aux autres modèles PyTorch du projet (state_dict seul
        # suffit) : ici n_features détermine la forme des couches et threshold
        # est indispensable à detect()  les trois doivent être restaurés
        # ensemble, sinon load_state_dict échouerait sur un mismatch de forme.
        torch.save({"state_dict": self.state_dict(), "n_features": self.n_features, "threshold": self._threshold}, path)
        logger.info("anomaly_detector.checkpoint_saved", path=str(path))

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path | str = DEFAULT_CHECKPOINT_PATH) -> "AnomalyDetector":
        path = Path(checkpoint_path)
        if not path.exists():
            logger.warning("anomaly_detector.checkpoint_missing_using_untrained_model", path=str(path))
            return cls()

        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = cls(n_features=checkpoint["n_features"])
        model.load_state_dict(checkpoint["state_dict"])
        model._threshold = checkpoint["threshold"]
        model.is_trained = True
        model.eval()
        logger.info("anomaly_detector.checkpoint_loaded", path=str(path))
        return model


__all__ = ["AnomalyDetector", "AnomalyResult", "DEFAULT_N_FEATURES"]
