"""Repository pour Client."""

from sqlalchemy import select

from backend.db.models.clients import Client
from backend.db.repositories.base_repository import BaseRepository


class ClientRepository(BaseRepository[Client]):
    model = Client

    async def get_by_name(self, name: str) -> Client | None:
        result = await self.session.execute(select(Client).where(Client.name == name))
        return result.scalar_one_or_none()
