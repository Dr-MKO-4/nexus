"""Configuration du logging structuré (JSON) de l'application.

Le niveau de verbosité, le format et la rotation des fichiers s'adaptent
à l'environnement courant (development / staging / production). En mode
développement, un handler console lisible est privilégié ; en production,
tout est émis en JSON pour être ingéré par la stack d'observabilité.

Le tracing des exécutions d'agents (spans, coûts, latences LLM) est délégué
à LangFuse, initialisé séparément via `get_langfuse_client()`.
"""

import json
import logging
import logging.config
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config.settings import settings

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "nexus.log"

# Niveau de log par environnement : verbeux en dev, silencieux en prod
_LEVEL_BY_ENVIRONMENT: dict[str, str] = {
    "development": "DEBUG",
    "staging": "INFO",
    "production": "WARNING",
}


class JsonFormatter(logging.Formatter):
    """Sérialise chaque enregistrement de log en une ligne JSON structurée."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
            "environment": settings.ENVIRONMENT,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Attributs additionnels passés via `logger.info(..., extra={...})`
        # (ex: agent_name, trace_id, task_id pour corréler avec LangFuse)
        for key, value in record.__dict__.items():
            if key.startswith("ctx_"):
                payload[key.removeprefix("ctx_")] = value

        return json.dumps(payload, ensure_ascii=False)


def _build_logging_config() -> dict[str, Any]:
    level = _LEVEL_BY_ENVIRONMENT.get(settings.ENVIRONMENT, "INFO")
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": JsonFormatter},
            "console": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                # Format lisible en développement, JSON structuré au-delà
                "formatter": "console" if settings.ENVIRONMENT == "development" else "json",
                "level": level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "filename": str(LOG_FILE),
                "maxBytes": 10 * 1024 * 1024,  # 10 Mo par fichier
                "backupCount": 5,
                "encoding": "utf-8",
                "level": level,
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": level,
        },
        "loggers": {
            # Bibliothèques tierces bruyantes : on les garde au-dessus du niveau applicatif
            "uvicorn.access": {"level": "WARNING", "propagate": True},
            "httpx": {"level": "WARNING", "propagate": True},
        },
    }


def setup_logging() -> None:
    """Initialise le logging applicatif. À appeler une seule fois au démarrage."""
    logging.config.dictConfig(_build_logging_config())


def get_langfuse_client():
    """Construit le client LangFuse utilisé pour tracer l'exécution des agents.

    Import différé pour éviter d'imposer la dépendance `langfuse` aux
    contextes qui n'ont pas besoin de tracing (ex: scripts utilitaires).
    """
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
    )
