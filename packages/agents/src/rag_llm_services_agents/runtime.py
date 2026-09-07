"""OpenAI Agents SDK integration helpers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from rag_llm_services_agents.prompts import (
    RAG_INSTRUCTIONS,
    ROUTER_INSTRUCTIONS,
    STUDY_INSTRUCTIONS,
)
from rag_llm_services_agents.tools import (
    DocumentContextInput,
    DocumentListInput,
    KnowledgeBaseTools,
    SearchKnowledgeBaseInput,
)


@dataclass(frozen=True)
class DeepSeekAgentsSdkConfig:
    """Configuration needed to build an OpenAI-compatible SDK model."""

    api_key: str
    base_url: str
    model: str
    api_mode: str = "responses"
    tracing_disabled: bool = True


@dataclass(frozen=True)
class SdkAgentSet:
    """OpenAI Agents SDK Agent objects for the three Phase 07 roles."""

    router: Any
    rag: Any
    study: Any


def build_deepseek_sdk_model(config: DeepSeekAgentsSdkConfig) -> Any:
    """Build an SDK model object for DeepSeek's OpenAI-compatible endpoint."""
    agents = _agents_module()
    set_tracing_disabled = getattr(agents, "set_tracing_disabled", None)
    if callable(set_tracing_disabled):
        set_tracing_disabled(disabled=config.tracing_disabled)

    normalized_base_url = config.base_url.strip().rstrip("/")
    if normalized_base_url.endswith("/v1"):
        raise ValueError("DeepSeek Agents SDK base_url must not include /v1")

    async_openai = agents.AsyncOpenAI
    client = async_openai(api_key=config.api_key, base_url=normalized_base_url)

    if config.api_mode == "responses":
        responses_model = getattr(agents, "OpenAIResponsesModel", None)
        if responses_model is None:
            raise RuntimeError("Installed openai-agents package lacks OpenAIResponsesModel")
        return responses_model(model=config.model, openai_client=client)
    if config.api_mode == "chat_completions":
        chat_model = agents.OpenAIChatCompletionsModel
        return chat_model(model=config.model, openai_client=client)
    raise ValueError("api_mode must be one of: responses, chat_completions")


def build_sdk_agent_set(*, model: Any | None = None, tools: list[Any] | None = None) -> SdkAgentSet:
    """Create SDK Agent definitions for RouterAgent, RAGAgent, and StudyAgent."""
    agents = _agents_module()
    agent_type = agents.Agent
    shared_tools = list(tools or [])
    return SdkAgentSet(
        router=agent_type(name="RouterAgent", instructions=ROUTER_INSTRUCTIONS, model=model),
        rag=agent_type(
            name="RAGAgent", instructions=RAG_INSTRUCTIONS, model=model, tools=shared_tools
        ),
        study=agent_type(
            name="StudyAgent",
            instructions=STUDY_INSTRUCTIONS,
            model=model,
            tools=shared_tools,
        ),
    )


def build_sdk_knowledge_tools(*, tools: KnowledgeBaseTools, owner_id: UUID) -> list[Any]:
    """Build OpenAI Agents SDK function tools with server-controlled owner scope."""

    async def search_knowledge_base(
        query: str,
        knowledge_base_id: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Search the current user's knowledge base and return cited source context."""
        output = await tools.search_knowledge_base(
            owner_id=owner_id,
            payload=SearchKnowledgeBaseInput(
                query=query,
                knowledge_base_id=UUID(knowledge_base_id) if knowledge_base_id else None,
                top_k=top_k,
            ),
        )
        return output.model_dump(mode="json")

    async def get_document_context(
        document_id: str,
        query: str = "document context",
        max_chunks: int = 5,
    ) -> dict[str, Any]:
        """Retrieve cited source context from one current-user document."""
        output = await tools.get_document_context(
            owner_id=owner_id,
            payload=DocumentContextInput(
                document_id=UUID(document_id),
                query=query,
                max_chunks=max_chunks,
            ),
        )
        return output.model_dump(mode="json")

    async def list_documents(
        knowledge_base_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List current-user documents without raw storage keys."""
        output = await tools.list_documents(
            owner_id=owner_id,
            payload=DocumentListInput(
                knowledge_base_id=UUID(knowledge_base_id) if knowledge_base_id else None,
                limit=limit,
            ),
        )
        return [document.model_dump(mode="json") for document in output]

    async def get_document_metadata(document_id: str) -> dict[str, Any]:
        """Fetch current-user document metadata without raw storage keys."""
        output = await tools.get_document_metadata(owner_id=owner_id, document_id=UUID(document_id))
        return output.model_dump(mode="json")

    return [
        sdk_function_tool(search_knowledge_base),
        sdk_function_tool(get_document_context),
        sdk_function_tool(list_documents),
        sdk_function_tool(get_document_metadata),
    ]


def sdk_function_tool(function: Any) -> Any:
    """Wrap a Python callable with the OpenAI Agents SDK function_tool decorator."""
    agents = _agents_module()
    function_tool = agents.function_tool
    return function_tool(function)


def _agents_module() -> Any:
    try:
        return importlib.import_module("agents")
    except ImportError as exc:
        raise RuntimeError("openai-agents is required for Phase 07 agent runtime") from exc
