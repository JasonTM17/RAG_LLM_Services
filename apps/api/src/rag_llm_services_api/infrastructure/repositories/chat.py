"""Repositories for owner-scoped conversations, messages, and LLM usage."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.conversation import ConversationModel, MessageModel
from rag_llm_services_api.db.models.llm_usage import LLMUsageModel
from rag_llm_services_llm.usage import LLMUsage


class ChatRepository:
    """Persistence boundary for local chat memory and usage audit rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_conversation(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
    ) -> ConversationModel | None:
        """Fetch a conversation scoped to owner."""
        result = await self._session.execute(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.owner_id == owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_conversation(
        self,
        *,
        owner_id: UUID,
        title: str,
    ) -> ConversationModel:
        """Create an owner-scoped conversation."""
        conversation = ConversationModel(id=uuid.uuid4(), owner_id=owner_id, title=title)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def add_message(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata_json: dict[str, object] | None = None,
    ) -> MessageModel:
        """Persist one message in a conversation."""
        message = MessageModel(
            id=uuid.uuid4(),
            owner_id=owner_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_json=metadata_json or {},
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_recent_messages(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        limit: int = 20,
    ) -> list[MessageModel]:
        """Return recent messages in chronological order."""
        result = await self._session.execute(
            select(MessageModel)
            .where(
                MessageModel.owner_id == owner_id,
                MessageModel.conversation_id == conversation_id,
            )
            .order_by(desc(MessageModel.created_at))
            .limit(limit)
        )
        messages = list(result.scalars().all())
        return list(reversed(messages))

    async def record_llm_usage(
        self,
        *,
        owner_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        provider: str,
        model: str,
        usage: LLMUsage,
        latency_ms: float,
        retry_count: int,
    ) -> LLMUsageModel:
        """Persist provider usage and estimated cost."""
        record = LLMUsageModel(
            id=uuid.uuid4(),
            owner_id=owner_id,
            conversation_id=conversation_id,
            message_id=message_id,
            provider=provider,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            latency_ms=latency_ms,
            retry_count=retry_count,
        )
        self._session.add(record)
        await self._session.flush()
        return record
