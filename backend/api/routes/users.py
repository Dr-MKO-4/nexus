"""Router users gestion réelle des comptes.

Corrige un écart trouvé lors d'un audit frontend/backend : Settings.tsx
(section "Utilisateurs") gérait une liste d'utilisateurs en `useState` LOCAL
uniquement aucun appel réseau, rien n'était persisté, rien ne reflétait
les vrais comptes en base. `UserRepository`/`User` (backend/db/repositories/
user_repository.py, backend/db/models/users.py) existaient déjà avec tout le
nécessaire (email, hashed_password, role, client_id, is_active) : ce router
les expose enfin.

Invitation (`POST /users`) : aucune infrastructure d'envoi d'email n'existe
dans ce projet (pas de service SMTP/transactionnel configuré ailleurs) un
mot de passe temporaire est donc généré et renvoyé UNE SEULE FOIS dans la
réponse, à communiquer manuellement par l'admin/manager qui crée le compte.
Documenté honnêtement comme limite plutôt que fabriquer un envoi d'email
qui n'existe pas réellement.
"""

import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr

from backend.api.auth import get_db_session, hash_password, require_role
from backend.db.models.enums import UserRole
from backend.db.models.users import User
from backend.db.repositories.user_repository import UserRepository

router = APIRouter(prefix="/users", tags=["users"])

_STRICT = ConfigDict(extra="forbid")
_MUTATE_ROLES = (UserRole.ADMIN, UserRole.MANAGER)


class UserOut(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    client_id: UUID | None
    is_active: bool


class UserCreate(BaseModel):
    model_config = _STRICT

    email: EmailStr
    role: UserRole
    client_id: UUID | None = None


class UserCreateResult(BaseModel):
    model_config = _STRICT

    user: UserOut
    temporary_password: str


class UserUpdate(BaseModel):
    model_config = _STRICT

    role: UserRole | None = None
    is_active: bool | None = None


def _authorize_client_scope(current_user: User, client_id: UUID | None) -> None:
    """MANAGER restreint à son propre client_id (ne peut ni voir ni créer de
    comptes pour un autre client) ; ADMIN (client_id NULL) sans restriction —
    même règle que campaigns._authorize_client_access."""
    if current_user.role != UserRole.ADMIN and current_user.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")


@router.get("", response_model=list[UserOut])
async def list_users(
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
    client_id: UUID | None = None,
) -> list[User]:
    repo = UserRepository(session)
    if current_user.role == UserRole.ADMIN:
        # ADMIN : tous les comptes si aucun filtre, ou ceux d'un client précis.
        if client_id is not None:
            return list(await repo.get_by_client(client_id))
        return list(await repo.list(limit=1000))
    # MANAGER : toujours restreint à son propre client_id, quel que soit le filtre demandé.
    _authorize_client_scope(current_user, current_user.client_id)
    return list(await repo.get_by_client(current_user.client_id))


@router.post("", response_model=UserCreateResult, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> UserCreateResult:
    _authorize_client_scope(current_user, body.client_id)
    repo = UserRepository(session)
    if await repo.get_by_email(body.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email.")

    temporary_password = secrets.token_urlsafe(12)
    user = await repo.create(
        email=body.email,
        hashed_password=hash_password(temporary_password),
        role=body.role,
        client_id=body.client_id,
        is_active=True,
    )
    return UserCreateResult(user=UserOut.model_validate(user), temporary_password=temporary_password)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> User:
    repo = UserRepository(session)
    target = await repo.get_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    _authorize_client_scope(current_user, target.client_id)

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return target
    updated = await repo.update(user_id, **fields)
    assert updated is not None
    return updated


__all__ = ["router"]
