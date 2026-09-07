"""Unit tests for EmbeddingProvider implementations: FakeEmbeddingProvider and BGEM3EmbeddingProvider."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from rag_llm_services_embeddings.base import EmbeddingProvider
from rag_llm_services_embeddings.bge_m3 import BGEM3EmbeddingProvider
from rag_llm_services_embeddings.fake import FakeEmbeddingProvider
from rag_llm_services_shared.errors import UpstreamUnavailableError

# -----------------------------------------------------------------------------
# FakeEmbeddingProvider tests
# -----------------------------------------------------------------------------


def test_fake_embedding_implements_protocol() -> None:
    provider = FakeEmbeddingProvider()
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 1024
    assert provider.model_name == "fake-bge-m3-deterministic"


async def test_fake_embedding_determinism_and_norm() -> None:
    provider = FakeEmbeddingProvider(dimension=1024)

    text_a = "Mô hình ngôn ngữ lớn tiếng Việt"
    text_b = "Large language model in English"

    vec_a1 = await provider.embed_query(text_a)
    vec_a2 = await provider.embed_query(text_a)
    vec_b = await provider.embed_query(text_b)

    # Deterministic: identical text gives identical vector
    assert vec_a1 == vec_a2
    assert len(vec_a1) == 1024

    # Distinct texts give different vectors
    assert vec_a1 != vec_b

    # Unit L2 norm
    norm_a = math.sqrt(sum(x * x for x in vec_a1))
    assert abs(norm_a - 1.0) < 1e-4

    norm_b = math.sqrt(sum(x * x for x in vec_b))
    assert abs(norm_b - 1.0) < 1e-4


async def test_fake_embedding_query_matches_documents_batch() -> None:
    provider = FakeEmbeddingProvider(batch_size=2)
    texts = [
        "Đoạn văn thứ nhất",
        "Đoạn văn thứ hai",
        "Đoạn văn thứ ba",
    ]

    docs_vecs = await provider.embed_documents(texts)
    assert len(docs_vecs) == 3

    for idx, text in enumerate(texts):
        single_vec = await provider.embed_query(text)
        assert docs_vecs[idx] == single_vec


async def test_fake_embedding_empty_inputs() -> None:
    provider = FakeEmbeddingProvider()
    empty_docs = await provider.embed_documents([])
    assert empty_docs == []

    empty_query = await provider.embed_query("")
    assert len(empty_query) == 1024


# -----------------------------------------------------------------------------
# BGEM3EmbeddingProvider tests
# -----------------------------------------------------------------------------


def test_bge_m3_implements_protocol() -> None:
    provider = BGEM3EmbeddingProvider(model_name="BAAI/bge-m3", device="cpu", batch_size=16)
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 1024
    assert provider.model_name == "BAAI/bge-m3"
    assert provider.device == "cpu"
    assert provider.batch_size == 16


async def test_bge_m3_with_injected_runner() -> None:
    calls: list[list[str]] = []

    def mock_runner(batch: list[str]) -> list[list[float]]:
        calls.append(batch)
        return [[0.1] * 1024 for _ in batch]

    provider = BGEM3EmbeddingProvider(
        model_name="test-bge-m3",
        batch_size=2,
        model_runner=mock_runner,
    )

    texts = ["Văn bản 1", "Văn bản 2", "Văn bản 3"]
    results = await provider.embed_documents(texts)

    assert len(results) == 3
    assert len(calls) == 2  # 2 batches: [2], [1]
    assert calls[0] == ["Văn bản 1", "Văn bản 2"]
    assert calls[1] == ["Văn bản 3"]

    query_vec = await provider.embed_query("Truy vấn thử nghiệm")
    assert len(query_vec) == 1024


async def test_bge_m3_raises_when_dependencies_missing() -> None:
    # Reset shared singleton state for isolated test
    BGEM3EmbeddingProvider._shared_model = None
    BGEM3EmbeddingProvider._shared_model_name = None

    provider = BGEM3EmbeddingProvider(model_name="BAAI/bge-m3-uninstalled")

    # Mock imports to fail
    with (
        patch.dict("sys.modules", {"FlagEmbedding": None, "sentence_transformers": None}),
        pytest.raises(UpstreamUnavailableError) as excinfo,
    ):
        await provider.embed_documents(["test text"])

    assert "BGE-M3 embedding model dependencies not installed" in str(excinfo.value)
