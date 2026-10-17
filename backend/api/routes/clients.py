"""Router clients sélecteur admin + persistance réelle de "Marque client"
et "Intégrations".

Corrige deux écarts trouvés lors d'un audit frontend/backend :

1. Limite structurelle : `User.client_id` est NULL pour un compte ADMIN
   (db/models/users.py)  `useActiveClientId()` renvoyait donc toujours
   `null` pour un admin, et TOUTES les pages scopées par client affichaient
   "Aucun client actif". Aucun endpoint "lister les clients" n'existait
   (`ClientRepository` n'avait que `get_by_name`). `GET /clients` comble ce
   manque, pour un sélecteur de client côté Header.

2. `Settings.tsx` ("Marque client", "Intégrations") gérait ces sections en
   `useState` LOCAL uniquement, alors que `Client.editorial_guidelines`/
   `brand_colors`/`logo_url`/`forbidden_topics` existent déjà en base (voir
   db/models/clients.py). `GET/PATCH /clients/{id}` les expose enfin.
   `integrations` (JSONB, migration 0002) stocke la config fournie par le
   client pour chaque service tiers  PAS un flux OAuth2 réel (documenté
   honnêtement dans le modèle et ci-dessous, pas fabriqué).
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from backend.api.auth import get_db_session, require_role
from backend.db.models.clients import Client
from backend.db.models.enums import UserRole
from backend.db.models.users import User
from backend.db.repositories.client_repository import ClientRepository

router = APIRouter(prefix="/clients", tags=["clients"])

_STRICT = ConfigDict(extra="forbid")
_MUTATE_ROLES = (UserRole.ADMIN, UserRole.MANAGER)


class ClientOut(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: UUID
    name: str
    industry: str | None
    website: str | None


class ClientDetailOut(ClientOut):
    editorial_guidelines: dict | None
    brand_colors: dict | None
    logo_url: str | None
    forbidden_topics: list[str] | None
    integrations: dict | None


class ClientBrandUpdate(BaseModel):
    model_config = _STRICT

    editorial_guidelines: dict | None = None
    brand_colors: dict | None = None
    logo_url: str | None = None
    forbidden_topics: list[str] | None = None


class ClientIntegrationsUpdate(BaseModel):
    model_config = _STRICT

    integrations: dict[str, Any]


def _authorize_client_access(current_user: User, client_id: UUID) -> None:
    if current_user.role != UserRole.ADMIN and current_user.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")


async def _get_client_or_404(session: Any, client_id: UUID) -> Client:
    client = await ClientRepository(session).get_by_id(client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client introuvable.")
    return client


@router.get("", response_model=list[ClientOut])
async def list_clients(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    session: Annotated[Any, Depends(get_db_session)],
) -> list[Client]:
    """Réservé ADMIN : un MANAGER/VIEWER connaît déjà son unique `client_id`
    (voir `/auth/me`), il n'a jamais besoin de lister tous les clients."""
    return list(await ClientRepository(session).list(limit=1000))


@router.get("/{client_id}", response_model=ClientDetailOut)
async def get_client(
    client_id: UUID,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Client:
    _authorize_client_access(current_user, client_id)
    return await _get_client_or_404(session, client_id)


@router.patch("/{client_id}/brand", response_model=ClientDetailOut)
async def update_client_brand(
    client_id: UUID,
    body: ClientBrandUpdate,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Client:
    _authorize_client_access(current_user, client_id)
    await _get_client_or_404(session, client_id)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return await _get_client_or_404(session, client_id)
    updated = await ClientRepository(session).update(client_id, **fields)
    assert updated is not None
    return updated


@router.patch("/{client_id}/integrations", response_model=ClientDetailOut)
async def update_client_integrations(
    client_id: UUID,
    body: ClientIntegrationsUpdate,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Client:
    """Fusionne (plutôt que remplace) `integrations` : un appel ne concernant
    qu'un seul service tiers ne doit pas effacer la config des autres déjà
    enregistrée."""
    _authorize_client_access(current_user, client_id)
    client = await _get_client_or_404(session, client_id)
    merged = {**(client.integrations or {}), **body.integrations}
    updated = await ClientRepository(session).update(client_id, integrations=merged)
    assert updated is not None
    return updated


__all__ = ["router"]
