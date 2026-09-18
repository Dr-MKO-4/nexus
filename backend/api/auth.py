"""Authentification JWT  Prompt 7.1.

Deux tokens distincts : un access token court (30 min par défaut,
`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) transmis en Authorization: Bearer sur
chaque requête, et un refresh token long (7 jours,
`JWT_REFRESH_TOKEN_EXPIRE_DAYS`) utilisé uniquement par POST /auth/refresh
pour obtenir un nouvel access token sans redemander le mot de passe. Les
deux sont des JWT signés HS256 avec `settings.SECRET_KEY`  pas de session
serveur, pas de table de tokens révoqués (hors périmètre de ce prompt).

`get_db_session` (dépendance FastAPI wrappant `backend.db.session.get_session`)
et `get_current_user`/`require_role` sont définis ici plutôt que dans un
module `dependencies.py` séparé (absent de la liste de fichiers du spec) :
tous les autres routers de Prompt 7.1 les importent directement depuis ce
module.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.db.models.enums import UserRole
from backend.db.models.users import User
from backend.db.repositories.user_repository import UserRepository
from backend.db.session import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_STRICT_CONFIG = ConfigDict(extra="forbid")

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_TOKEN_TYPE_ACCESS = "access"
_TOKEN_TYPE_REFRESH = "refresh"


class TokenResponse(BaseModel):
    model_config = _STRICT_CONFIG

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    model_config = _STRICT_CONFIG

    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    model_config = _STRICT_CONFIG

    id: UUID
    email: str
    role: UserRole
    client_id: UUID | None
    is_active: bool


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(*, subject: str, token_type: str, expires_delta: timedelta, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    return _create_token(
        subject=str(user.id),
        token_type=_TOKEN_TYPE_ACCESS,
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"role": user.role.value, "client_id": str(user.client_id) if user.client_id else None},
    )


def create_refresh_token(user: User) -> str:
    return _create_token(
        subject=str(user.id),
        token_type=_TOKEN_TYPE_REFRESH,
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def _decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide ou expiré.") from exc

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Type de token invalide (attendu : {expected_type!r}).")
    return payload


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


async def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    payload = _decode_token(token, expected_type=_TOKEN_TYPE_ACCESS)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sans sujet (sub).")

    user = await UserRepository(session).get_by_id(UUID(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable ou inactif.")
    return user


def require_role(*allowed_roles: UserRole):
    """Fabrique de dépendance FastAPI : `Depends(require_role(UserRole.ADMIN))`
    lève 403 si `current_user.role` n'est pas dans `allowed_roles`. Une
    fabrique (pas une dépendance unique) : chaque route a un jeu de rôles
    autorisés différent (spec : "vérification des rôles par route"), une
    seule dépendance figée ne pourrait pas paramétrer ça par route."""

    async def _check(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle {current_user.role.value!r} non autorisé pour cette action (requis : {[r.value for r in allowed_roles]}).",
            )
        return current_user

    return _check


def _issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user), refresh_token=create_refresh_token(user))


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """`OAuth2PasswordRequestForm` impose `username`/`password` (form-encodé,
    pas JSON)  convention FastAPI standard pour rester compatible avec
    `OAuth2PasswordBearer`/Swagger UI. `username` reçoit l'email ici (le
    modèle User n'a pas de champ `username` distinct)."""
    repo = UserRepository(session)
    user = await repo.get_by_email(form_data.username)
    if user is None or not user.is_active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect.")

    await repo.update(user.id, last_login_at=datetime.now(timezone.utc))
    logger.info("auth.login_succeeded", user_id=str(user.id), role=user.role.value)
    return _issue_tokens(user)


class RefreshRequest(BaseModel):
    model_config = _STRICT_CONFIG

    refresh_token: str


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AccessTokenResponse:
    payload = _decode_token(body.refresh_token, expected_type=_TOKEN_TYPE_REFRESH)
    user = await UserRepository(session).get_by_id(UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable ou inactif.")

    logger.info("auth.token_refreshed", user_id=str(user.id))
    return AccessTokenResponse(access_token=create_access_token(user))


@router.get("/me", response_model=UserProfile)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserProfile:
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        client_id=current_user.client_id,
        is_active=current_user.is_active,
    )


__all__ = [
    "router",
    "get_db_session",
    "get_current_user",
    "require_role",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
]
