"""Repository générique async : opérations CRUD de base partagées par tous
les repositories spécifiques au domaine (voir les autres fichiers de ce module)."""

from collections.abc import Sequence
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """CRUD générique. Chaque sous-classe fixe `model` sur le type concret qu'elle gère."""

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields: Any) -> ModelType:
        obj = self.model(**fields)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def get_by_id(self, id_: UUID) -> ModelType | None:
        return await self.session.get(self.model, id_)

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        result = await self.session.execute(
            select(self.model).order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return result.scalar_one()

    async def update(self, id_: UUID, **fields: Any) -> ModelType | None:
        obj = await self.get_by_id(id_)
        if obj is None:
            return None
        for key, value in fields.items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, id_: UUID) -> bool:
        obj = await self.get_by_id(id_)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    async def exists(self, id_: UUID) -> bool:
        return await self.get_by_id(id_) is not None
