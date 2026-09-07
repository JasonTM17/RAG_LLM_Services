"""OpenAI Agents SDK runtime smoke tests."""

import uuid

import pytest

from rag_llm_services_agents.runtime import (
    DeepSeekAgentsSdkConfig,
    build_deepseek_sdk_model,
    build_sdk_agent_set,
    build_sdk_knowledge_tools,
)
from rag_llm_services_agents.tools import KnowledgeBaseTools
from rag_llm_services_rag.retrieval.types import ContextBundle


class FakeRetrievalPort:
    async def search(self, **kwargs):
        del kwargs
        return type("RetrievalResponse", (), {"context_bundle": ContextBundle(context_text="")})()


class FakeDocumentCatalog:
    async def list_documents(self, **kwargs):
        del kwargs
        return []

    async def get_document_metadata(self, **kwargs):
        del kwargs


def test_build_sdk_agent_set_creates_named_agents() -> None:
    agents = build_sdk_agent_set()

    assert agents.router.name == "RouterAgent"
    assert agents.rag.name == "RAGAgent"
    assert agents.study.name == "StudyAgent"


def test_deepseek_sdk_model_uses_responses_model_without_network() -> None:
    model = build_deepseek_sdk_model(
        DeepSeekAgentsSdkConfig(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        )
    )

    assert type(model).__name__ == "OpenAIResponsesModel"


def test_deepseek_sdk_model_rejects_v1_suffix() -> None:
    with pytest.raises(ValueError, match="/v1"):
        build_deepseek_sdk_model(
            DeepSeekAgentsSdkConfig(
                api_key="test-key",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-v4-flash",
            )
        )


def test_build_sdk_knowledge_tools_exposes_bounded_tool_names() -> None:
    tools = KnowledgeBaseTools(
        retrieval_service=FakeRetrievalPort(),
        document_catalog=FakeDocumentCatalog(),
    )
    sdk_tools = build_sdk_knowledge_tools(tools=tools, owner_id=uuid.uuid4())

    assert [tool.name for tool in sdk_tools] == [
        "search_knowledge_base",
        "get_document_context",
        "list_documents",
        "get_document_metadata",
    ]
