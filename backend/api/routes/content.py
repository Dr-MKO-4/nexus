"""Router contenus  Prompt 7.1.

`POST /contents/{id}/publish` : le seul canal de publication CONNECTÉ à un
mécanisme réel dans ce projet est le social (`publish_social_post_task`,
Prompt 6.1, via l'Agent Social)  aucun client CMS/API de publication web
autonome, ni endpoint d'envoi d'un `Content` EMAIL isolé (distinct d'une
séquence email complète, voir `send_email_sequence_task`) n'existe. Pour
WEB/EMAIL, "publier immédiatement" ne peut donc réellement signifier que
"marquer publié en base"  limite honnête du périmètre déjà construit,
documentée plutôt que masquée par un faux appel de dispatch.
"""

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from backend.api.auth import get_current_user, get_db_session, require_role
from backend.db.models.content import Content
from backend.db.models.enums import ContentPlatform, ContentStatus, ContentType, UserRole
from backend.db.models.users import User
from backend.db.repositories.content_repository import ContentRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/contents", tags=["contents"])

_STRICT = ConfigDict(extra="forbid")
_MUTATE_ROLES = (UserRole.ADMIN, UserRole.MANAGER)
_SOCIAL_PLATFORMS = (ContentPlatform.LINKEDIN, ContentPlatform.META, ContentPlatform.TIKTOK)


class ContentOut(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    id: UUID
    client_id: UUID
    campaign_id: UUID | None
    agent_source: str
    content_type: ContentType
    title: str | None
    body: str
    platform: ContentPlatform
    status: ContentStatus
    performance_data: dict | None
    published_at: datetime | None
    scheduled_at: datetime | None


class ContentUpdate(BaseModel):
    model_config = _STRICT

    title: str | None = None
    body: str | None = None
    status: ContentStatus | None = None


class ScheduleRequest(BaseModel):
    model_config = _STRICT

    scheduled_at: datetime


def _authorize_client_access(current_user: User, client_id: UUID) -> None:
    if current_user.role != UserRole.ADMIN and current_user.client_id != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès interdit à ce client.")


async def _get_content_or_404(session: Any, content_id: UUID) -> Content:
    content = await ContentRepository(session).get_by_id(content_id)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contenu introuvable.")
    return content


@router.get("/calendar", response_model=list[ContentOut])
async def get_calendar(
    client_id: UUID,
    start: datetime,
    end: datetime,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> list[Content]:
    """Enregistrée AVANT `/{content_id}` : sans cet ordre, FastAPI tenterait
    de faire correspondre "calendar" au segment `{content_id}` (UUID) de la
    route suivante et échouerait en 422 plutôt que d'atteindre cette route."""
    _authorize_client_access(current_user, client_id)
    return list(await ContentRepository(session).get_calendar(client_id, start, end))


@router.get("", response_model=list[ContentOut])
async def list_contents(
    client_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
    content_type: ContentType | None = Query(default=None),
    content_status: ContentStatus | None = Query(default=None, alias="status"),
    limit: int = 100,
    offset: int = 0,
) -> list[Content]:
    _authorize_client_access(current_user, client_id)
    contents = await ContentRepository(session).get_by_client(client_id, limit=limit, offset=offset)
    if content_type is not None:
        contents = [c for c in contents if c.content_type == content_type]
    if content_status is not None:
        contents = [c for c in contents if c.status == content_status]
    return contents


@router.get("/{content_id}", response_model=ContentOut)
async def get_content(
    content_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_db_session)],
) -> Content:
    content = await _get_content_or_404(session, content_id)
    _authorize_client_access(current_user, content.client_id)
    return content


@router.patch("/{content_id}", response_model=ContentOut)
async def update_content(
    content_id: UUID,
    body: ContentUpdate,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Content:
    content = await _get_content_or_404(session, content_id)
    _authorize_client_access(current_user, content.client_id)

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return content
    updated = await ContentRepository(session).update(content_id, **fields)
    assert updated is not None
    logger.info("contents.updated", content_id=str(content_id), fields=list(fields))
    return updated


@router.post("/{content_id}/publish", response_model=ContentOut)
async def publish_content(
    content_id: UUID,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Content:
    content = await _get_content_or_404(session, content_id)
    _authorize_client_access(current_user, content.client_id)

    if content.platform in _SOCIAL_PLATFORMS:
        from backend.tasks.workers.marketing_worker import publish_social_post_task

        publish_social_post_task.delay(content_id=str(content_id), platforms=[content.platform.value])
        logger.info("contents.publish_dispatched_social", content_id=str(content_id), platform=content.platform.value)
        return content

    # WEB/EMAIL : aucun mécanisme de dispatch dédié (voir docstring de module)
    #  marque directement comme publié.
    updated = await ContentRepository(session).update(
        content_id, status=ContentStatus.PUBLISHED, published_at=datetime.now(timezone.utc)
    )
    assert updated is not None
    logger.info("contents.published_directly", content_id=str(content_id), platform=content.platform.value)
    return updated


@router.post("/{content_id}/schedule", response_model=ContentOut)
async def schedule_content(
    content_id: UUID,
    body: ScheduleRequest,
    current_user: Annotated[User, Depends(require_role(*_MUTATE_ROLES))],
    session: Annotated[Any, Depends(get_db_session)],
) -> Content:
    content = await _get_content_or_404(session, content_id)
    _authorize_client_access(current_user, content.client_id)

    if body.scheduled_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_at doit être dans le futur.")

    if content.platform in _SOCIAL_PLATFORMS:
        from backend.tasks.workers.marketing_worker import publish_social_post_task

        # `eta=` (pas `countdown=`) : Celery calcule lui-même le délai à
        # partir d'un instant absolu  l'API publique de apply_async pour ce
        # cas d'usage (voir la doc Celery, `eta` vs `countdown`).
        publish_social_post_task.apply_async(
            kwargs={"content_id": str(content_id), "platforms": [content.platform.value]}, eta=body.scheduled_at
        )
        logger.info("contents.schedule_dispatched_social", content_id=str(content_id), scheduled_at=body.scheduled_at.isoformat())
    else:
        logger.info("contents.scheduled_no_dispatch", content_id=str(content_id), platform=content.platform.value)

    updated = await ContentRepository(session).update(content_id, scheduled_at=body.scheduled_at)
    assert updated is not None
    return updated


__all__ = ["router"]
