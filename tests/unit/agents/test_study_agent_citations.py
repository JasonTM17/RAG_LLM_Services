"""StudyAgent citation validation regression tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from rag_llm_services_agents.citations import CitationValidationError
from rag_llm_services_agents.study_agent import StudyAgent, StudyDifficulty
from rag_llm_services_agents.tools import KnowledgeBaseTools
from rag_llm_services_llm.deepseek import FakeLLMProvider
from rag_llm_services_rag.retrieval.types import CitedChunk, ContextBundle


class FakeRetrievalPort:
    async def search(self, **kwargs):
        del kwargs
        return SimpleNamespace(
            context_bundle=ContextBundle(
                context_text="[S1] Source: study.md\nGrounded fact.",
                cited_chunks=[
                    CitedChunk(
                        source_id="[S1]",
                        chunk_id=uuid.uuid4(),
                        document_id=uuid.uuid4(),
                        content="Grounded fact.",
                        filename="study.md",
                    )
                ],
            )
        )


class FakeDocumentCatalog:
    async def list_documents(self, **kwargs):
        del kwargs
        return []

    async def get_document_metadata(self, **kwargs):
        del kwargs


@pytest.mark.asyncio
async def test_study_agent_rejects_invented_citations_inside_text_fields() -> None:
    provider = FakeLLMProvider(
        structured_payload={
            "topic": "study workflows",
            "difficulty": "intermediate",
            "questions": [
                {
                    "question": "Which source proves this invented claim [S9]?",
                    "choices": ["Grounded [S1]", "Invented [S9]"],
                    "answer": "Grounded [S1]",
                    "explanation": "The explanation cites an unavailable source [S9].",
                    "citations": ["[S1]"],
                }
            ],
        }
    )
    agent = StudyAgent(
        tools=KnowledgeBaseTools(
            retrieval_service=FakeRetrievalPort(),
            document_catalog=FakeDocumentCatalog(),
        ),
        llm_provider=provider,
    )

    with pytest.raises(CitationValidationError):
        await agent.quiz(
            owner_id=uuid.uuid4(),
            topic="study workflows",
            question_count=1,
            difficulty=StudyDifficulty.INTERMEDIATE,
        )
