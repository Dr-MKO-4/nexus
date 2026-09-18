"""Modèles de détection d'anomalies sur les métriques marketing (trafic, conversions, dépenses)."""

from backend.pytorch_models.anomaly.anomaly_detector import AnomalyDetector, AnomalyResult, DEFAULT_N_FEATURES

__all__ = ["AnomalyDetector", "AnomalyResult", "DEFAULT_N_FEATURES"]
