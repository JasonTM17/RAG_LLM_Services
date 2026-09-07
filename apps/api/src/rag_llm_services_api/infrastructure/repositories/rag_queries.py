"""Repository for persisting and querying retrieval audit events."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag_llm_services_api.db.models.rag_query import RagQueryModel


class RagQueryRepository:
    """Repository managing retrieval query event records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_query(
        self,
        owner_id: UUID,
        query_text: str,
        retrieval_method: str,
        result_count: int,
        latency_ms: float,
        result_chunk_ids: list[str] | list[UUID],
        knowledge_base_id: UUID | None = None,
        vector_top_k: int = 10,
        keyword_top_k: int = 10,
        rerank_top_k: int = 8,
        filter_json: dict[str, Any] | None = None,
        stage_latencies_ms: dict[str, float] | None = None,
    ) -> RagQueryModel:
        """Persist a retrieval query execution record for auditing and evaluation."""
        str_chunk_ids = [str(cid) for cid in result_chunk_ids]
        rounded_stage_latencies = {
            name: round(value, 2) for name, value in (stage_latencies_ms or {}).items()
        }
        model = RagQueryModel(
            id=uuid.uuid4(),
            owner_id=owner_id,
            query_text=query_text,
            knowledge_base_id=knowledge_base_id,
            retrieval_method=retrieval_method,
            vector_top_k=vector_top_k,
            keyword_top_k=keyword_top_k,
            rerank_top_k=rerank_top_k,
            result_count=result_count,
            latency_ms=round(latency_ms, 2),
            filter_json=filter_json or {},
            stage_latencies_ms=rounded_stage_latencies,
            result_chunk_ids=str_chunk_ids,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_queries_by_owner(
        self,
        owner_id: UUID,
        limit: int = 50,
    ) -> Sequence[RagQueryModel]:
        """Fetch historical retrieval query events for an owner ordered by recency."""
        stmt = (
            select(RagQueryModel)
            .where(RagQueryModel.owner_id == owner_id)
            .order_by(RagQueryModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
