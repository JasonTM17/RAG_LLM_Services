"""Repository for registered user accounts."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.user import UserModel


class UserRepository:
    """Small data-access surface for account rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.email == email)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: object) -> UserModel | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str) -> UserModel:
        user = UserModel(email=email, password_hash=password_hash)
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            raise
        await self._session.refresh(user)
        return user


__all__ = [
    "UserRepository",
]
