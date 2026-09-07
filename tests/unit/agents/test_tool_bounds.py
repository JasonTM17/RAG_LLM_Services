"""Bounded knowledge tool tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from rag_llm_services_agents.tools import (
    AgentToolLimits,
    DocumentListInput,
    DocumentMetadata,
    KnowledgeBaseTools,
    SearchKnowledgeBaseInput,
)
from rag_llm_services_rag.retrieval.types import CitedChunk, ContextBundle, RetrievalMethod


class FakeRetrievalPort:
    def __init__(self, bundle: ContextBundle) -> None:
        self.bundle = bundle
        self.calls: list[dict[str, object]] = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(context_bundle=self.bundle)


class FakeDocumentCatalog:
    def __init__(self, documents: list[DocumentMetadata]) -> None:
        self.documents = documents

    async def list_documents(
        self,
        *,
        owner_id: UUID,
        knowledge_base_id: UUID | None,
        limit: int,
    ) -> list[DocumentMetadata]:
        del owner_id, knowledge_base_id
        return self.documents[:limit]

    async def get_document_metadata(
        self,
        *,
        owner_id: UUID,
        document_id: UUID,
    ) -> DocumentMetadata | None:
        del owner_id
        return next((doc for doc in self.documents if doc.id == document_id), None)


@pytest.mark.asyncio
async def test_search_tool_enforces_owner_scope_and_bounds_output() -> None:
    owner_id = uuid.uuid4()
    sources = [
        CitedChunk(
            source_id=f"[S{idx}]",
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content="x" * 300,
            filename=f"doc-{idx}.md",
            retrieval_method=RetrievalMethod.HYBRID,
        )
        for idx in range(1, 5)
    ]
    bundle = ContextBundle(
        context_text=" ".join(chunk.content for chunk in sources),
        cited_chunks=sources,
        total_tokens=100,
        total_chunks=len(sources),
        max_budget=6000,
    )
    tools = KnowledgeBaseTools(
        retrieval_service=FakeRetrievalPort(bundle),
        document_catalog=FakeDocumentCatalog([]),
        limits=AgentToolLimits(max_results=2, max_context_chunks=2, max_chunk_chars=200),
    )

    output = await tools.search_knowledge_base(
        owner_id=owner_id,
        payload=SearchKnowledgeBaseInput(query="rag", top_k=10),
    )

    assert tools._retrieval_service.calls[0]["owner_id"] == owner_id
    assert tools._retrieval_service.calls[0]["rerank_top_k"] == 2
    assert len(output.sources) == 2
    assert all(len(source.content) <= 200 for source in output.sources)
    assert all("[truncated]" in source.content for source in output.sources)
    assert output.sources[0].source_id == "[S1]"


@pytest.mark.asyncio
async def test_list_documents_tool_bounds_catalog_results() -> None:
    now = datetime.now(UTC)
    docs = [
        DocumentMetadata(
            id=uuid.uuid4(),
            knowledge_base_id=uuid.uuid4(),
            filename=f"doc-{idx}.md",
            content_type="text/markdown",
            status="INDEXED",
            created_at=now,
            updated_at=now,
        )
        for idx in range(5)
    ]
    tools = KnowledgeBaseTools(
        retrieval_service=FakeRetrievalPort(ContextBundle(context_text="")),
        document_catalog=FakeDocumentCatalog(docs),
        limits=AgentToolLimits(max_documents=2),
    )

    output = await tools.list_documents(
        owner_id=uuid.uuid4(),
        payload=DocumentListInput(limit=100),
    )

    assert len(output) == 2
