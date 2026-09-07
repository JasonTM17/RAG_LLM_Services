"""RAG agent orchestration over bounded knowledge tools."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from rag_llm_services_agents.citations import CitationValidator
from rag_llm_services_agents.context_window import ContextWindowManager, HistoryMessage
from rag_llm_services_agents.prompts import RAG_INSTRUCTIONS, build_rag_user_prompt
from rag_llm_services_agents.tools import KnowledgeBaseTools, SearchKnowledgeBaseInput, SourceChunk
from rag_llm_services_llm.base import LLMMessage, LLMProvider, LLMRequest, MessageRole
from rag_llm_services_llm.usage import LLMUsage


@dataclass(frozen=True)
class RAGAgentResult:
    """Completed RAG agent answer."""

    answer: str
    citations: list[SourceChunk]
    retrieved_sources: list[SourceChunk]
    usage: LLMUsage
    provider: str
    model: str
    latency_ms: float


class RAGAgent:
    """Answer with retrieval context while preserving citation and scope boundaries."""

    def __init__(
        self,
        *,
        tools: KnowledgeBaseTools,
        llm_provider: LLMProvider,
        citation_validator: CitationValidator | None = None,
        context_window: ContextWindowManager | None = None,
    ) -> None:
        self._tools = tools
        self._llm_provider = llm_provider
        self._citation_validator = citation_validator or CitationValidator()
        self._context_window = context_window or ContextWindowManager()

    async def answer(
        self,
        *,
        owner_id: UUID,
        question: str,
        conversation_history: Sequence[HistoryMessage | tuple[str, str]] | None = None,
        knowledge_base_id: UUID | None = None,
        max_output_tokens: int | None = None,
        context_token_budget: int | None = None,
        idempotency_key: str | None = None,
    ) -> RAGAgentResult:
        tool_output = await self._tools.search_knowledge_base(
            owner_id=owner_id,
            payload=SearchKnowledgeBaseInput(
                query=question,
                knowledge_base_id=knowledge_base_id,
                context_token_budget=context_token_budget,
                top_k=self._tools.limits.max_results,
            ),
        )
        selected_history = self._context_window.select(conversation_history or [])
        messages = (
            LLMMessage(role=MessageRole.SYSTEM, content=RAG_INSTRUCTIONS),
            LLMMessage(
                role=MessageRole.USER,
                content=build_rag_user_prompt(
                    question=question,
                    context_text=tool_output.context_text,
                    history=selected_history.messages,
                ),
            ),
        )
        response = await self._llm_provider.complete(
            LLMRequest(
                messages=messages,
                max_output_tokens=max_output_tokens,
                idempotency_key=idempotency_key,
            )
        )
        context_bundle = tool_output.to_context_bundle()
        self._citation_validator.validate(
            response.content,
            context_bundle,
            require_citation=bool(context_bundle.cited_chunks),
        )
        cited_ids = set(self._citation_validator.extract_source_ids(response.content))
        citations = [source for source in tool_output.sources if source.source_id in cited_ids]
        return RAGAgentResult(
            answer=response.content,
            citations=citations,
            retrieved_sources=tool_output.sources,
            usage=response.usage,
            provider=response.provider,
            model=response.model,
            latency_ms=response.latency_ms,
        )
