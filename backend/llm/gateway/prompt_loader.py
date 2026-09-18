"""Chargement de prompts versionnés via LangFuse Prompt Management, avec
repli automatique sur une constante Python locale.

Partagé par le prompts.py de chaque agent (orchestrateur, SEO, SEA,
Content...) : chacun garde ses propres constantes de prompt et son propre
mapping nom -> fallback, mais la mécanique de récupération/interpolation est
commune  évite de dupliquer ce module dans chaque agents/<nom>/prompts.py.
"""

import re
from collections.abc import Mapping

import structlog

from backend.config.settings import settings

logger = structlog.get_logger(__name__)

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def compile_template(template: str, variables: Mapping[str, object]) -> str:
    """Interpolation `{{variable}}`  même syntaxe que LangFuse Prompt
    Management (vérifié dans le SDK : `langfuse.model.TemplateParser`), pour
    qu'un fallback local soit copiable tel quel dans l'UI LangFuse. Une
    variable absente de `variables` est laissée telle quelle plutôt que de
    lever une exception."""

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        return str(variables[name]) if name in variables else match.group(0)

    return _VARIABLE_PATTERN.sub(_replace, template)


def get_prompt(name: str, fallback: str, **variables: object) -> str:
    """Récupère un prompt versionné depuis LangFuse (`name`), avec repli sur
    `fallback` si LangFuse est injoignable ou mal configuré. Retourne le
    texte déjà interpolé avec `variables`."""
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        prompt_client = client.get_prompt(name, type="text", fallback=fallback)
        return prompt_client.compile(**variables)
    except Exception as exc:
        logger.warning("prompt_loader.langfuse_unavailable", prompt=name, error=str(exc))
        return compile_template(fallback, variables)
