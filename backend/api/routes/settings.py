"""Router settings  statut réel des providers LLM.

Corrige un écart trouvé lors d'un audit frontend/backend : Settings.tsx
affichait un statut Groq/Together AI/Fireworks AI/Mistral CODÉ EN DUR
(`{name: "Groq", online: true}`, etc.), sans AUCUN endpoint backend
correspondant  donc jamais réellement synchronisé avec l'état des clés API
configurées. Ce router expose :
- un statut réel ("configuré" = clé API présente dans settings, pas un
  simple flag inventé) ;
- un test de connectivité réel (bouton "Tester" du frontend) : un appel
  litellm minimal (1 complétion de 5 tokens max) directement au provider
  concerné, PAS via le Router LiteLLM complet (celui-ci fait du fallback
  automatique entre providers  inutile et contre-productif ici, où le but
  est justement de tester UN provider précis, isolément).
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from backend.api.auth import get_current_user, require_role
from backend.db.models.enums import UserRole
from backend.db.models.users import User
from backend.llm.providers import fireworks, groq, mistral, together

router = APIRouter(prefix="/settings/llm", tags=["settings"])

_STRICT = ConfigDict(extra="forbid")

# Mêmes 4 providers API que litellm_config._collect_provider_configs (voir
# backend/llm/gateway/litellm_config.py)  noms alignés sur ceux déjà
# utilisés partout ailleurs dans ce projet (ex. _API_FALLBACK_ORDER).
_PROVIDERS = {
    "groq": groq,
    "together_ai": together,
    "fireworks_ai": fireworks,
    "mistral": mistral,
}

_MUTATE_ROLES = (UserRole.ADMIN, UserRole.MANAGER)


class ProviderStatus(BaseModel):
    model_config = _STRICT

    name: str
    configured: bool
    default_model: str


class ProviderTestResult(BaseModel):
    model_config = _STRICT

    name: str
    success: bool
    latency_ms: float | None
    error: str | None


@router.get("/providers", response_model=list[ProviderStatus])
async def list_provider_status(current_user: Annotated[User, Depends(get_current_user)]) -> list[ProviderStatus]:
    """"Disponible" = clé API configurée  pas un ping réseau à chaque
    chargement de page (coûterait une requête par provider à chaque
    affichage des Réglages) : le test de connectivité réel est un acte
    explicite (POST .../test), pas un effet de bord d'un simple GET."""
    results: list[ProviderStatus] = []
    for name, module in _PROVIDERS.items():
        config = module.get_provider_config()
        results.append(
            ProviderStatus(name=name, configured=bool(config.get("api_key")), default_model=config["models"]["default"])
        )
    return results


@router.post("/providers/{name}/test", response_model=ProviderTestResult)
async def test_provider(
    name: str,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
) -> ProviderTestResult:
    """Réservé ADMIN/MANAGER (contrairement au GET ci-dessus) : ce test
    déclenche un VRAI appel facturable au provider, pas une simple lecture."""
    module = _PROVIDERS.get(name)
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider inconnu : {name!r}. Valides : {sorted(_PROVIDERS)}")

    config = module.get_provider_config()
    if not config.get("api_key"):
        return ProviderTestResult(name=name, success=False, latency_ms=None, error="Clé API non configurée.")

    import litellm

    start = time.perf_counter()
    try:
        await litellm.acompletion(
            model=config["models"]["default"],
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            api_key=config["api_key"],
            timeout=10,
        )
        return ProviderTestResult(name=name, success=True, latency_ms=round((time.perf_counter() - start) * 1000, 1), error=None)
    except Exception as exc:
        return ProviderTestResult(
            name=name, success=False, latency_ms=round((time.perf_counter() - start) * 1000, 1), error=str(exc)[:300]
        )


__all__ = ["router"]
