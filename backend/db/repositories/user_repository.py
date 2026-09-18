"""Repository pour User."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from backend.db.models.users import User
from backend.db.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_active_by_client(self, client_id: UUID) -> Sequence[User]:
        result = await self.session.execute(
            select(User).where(User.client_id == client_id, User.is_active.is_(True))
        )
        return result.scalars().all()

    async def get_by_client(self, client_id: UUID) -> Sequence[User]:
        """Tous les comptes d'un client (actifs ou non)  distinct de
        `get_active_by_client` ci-dessus, nécessaire à la gestion des
        utilisateurs (backend/api/routes/users.py), où un admin/manager doit
        aussi voir les comptes désactivés pour pouvoir les réactiver."""
        result = await self.session.execute(select(User).where(User.client_id == client_id))
        return result.scalars().all()
