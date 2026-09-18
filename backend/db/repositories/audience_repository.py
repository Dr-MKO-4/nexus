"""Repositories pour Contact et EmailSequence."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from backend.db.models.audiences import Contact, EmailSequence
from backend.db.models.enums import EmailSequenceStatus
from backend.db.repositories.base_repository import BaseRepository


class ContactRepository(BaseRepository[Contact]):
    model = Contact

    async def get_by_client(
        self, client_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Contact]:
        result = await self.session.execute(
            select(Contact)
            .where(Contact.client_id == client_id)
            .order_by(Contact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_email(self, client_id: UUID, email: str) -> Contact | None:
        result = await self.session.execute(
            select(Contact).where(Contact.client_id == client_id, Contact.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_segment(self, client_id: UUID, tag: str) -> Sequence[Contact]:
        result = await self.session.execute(
            select(Contact).where(
                Contact.client_id == client_id,
                Contact.segment_tags.contains([tag]),
            )
        )
        return result.scalars().all()

    async def get_active_leads(self, client_id: UUID, min_score: int = 50) -> Sequence[Contact]:
        result = await self.session.execute(
            select(Contact).where(
                Contact.client_id == client_id,
                Contact.opted_out.is_(False),
                Contact.lead_score >= min_score,
            )
        )
        return result.scalars().all()


class EmailSequenceRepository(BaseRepository[EmailSequence]):
    model = EmailSequence

    async def get_by_client(
        self, client_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[EmailSequence]:
        """EmailSequence n'a pas de colonne `client_id` propre (l'isolation
        multi-tenant passe par son `contact_id` -> Contact.client_id)  join
        nécessaire, contrairement aux autres `get_by_client` du projet."""
        result = await self.session.execute(
            select(EmailSequence)
            .join(Contact, EmailSequence.contact_id == Contact.id)
            .where(Contact.client_id == client_id)
            .order_by(EmailSequence.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_active_for_contact(self, contact_id: UUID) -> Sequence[EmailSequence]:
        result = await self.session.execute(
            select(EmailSequence).where(
                EmailSequence.contact_id == contact_id,
                EmailSequence.status.in_(
                    [EmailSequenceStatus.PENDING, EmailSequenceStatus.IN_PROGRESS]
                ),
            )
        )
        return result.scalars().all()

    async def has_received_sequence(self, contact_id: UUID, sequence_name: str) -> bool:
        result = await self.session.execute(
            select(EmailSequence).where(
                EmailSequence.contact_id == contact_id,
                EmailSequence.sequence_name == sequence_name,
            )
        )
        return result.scalar_one_or_none() is not None
