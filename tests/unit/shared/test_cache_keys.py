"""Tests for safe cache key construction."""

from __future__ import annotations

import uuid

from rag_llm_services_shared.cache_keys import retrieval_cache_key, stable_sha256


def test_stable_sha256_is_deterministic_hex_digest() -> None:
    digest = stable_sha256("same input")

    assert digest == stable_sha256("same input")
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_retrieval_cache_key_hashes_query_and_owner_scope() -> None:
    owner_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    owner_b = uuid.UUID("00000000-0000-0000-0000-000000000002")
    sensitive_query = "How do I debug customer alpha outage?"

    key_a = retrieval_cache_key(owner_id=owner_a, query=sensitive_query)
    key_b = retrieval_cache_key(owner_id=owner_b, query=sensitive_query)

    assert key_a.startswith("rag:retrieval:v1:")
    assert sensitive_query not in key_a
    assert "customer alpha" not in key_a
    assert str(owner_a) not in key_a
    assert key_a != key_b


def test_retrieval_cache_key_normalizes_query_and_sorts_document_scope() -> None:
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    doc_a = uuid.UUID("00000000-0000-0000-0000-000000000010")
    doc_b = uuid.UUID("00000000-0000-0000-0000-000000000020")

    key_1 = retrieval_cache_key(
        owner_id=owner_id,
        query="  Vietnamese RAG  ",
        document_ids=[doc_b, doc_a],
    )
    key_2 = retrieval_cache_key(
        owner_id=owner_id,
        query="vietnamese rag",
        document_ids=[doc_a, doc_b],
    )

    assert key_1 == key_2


def test_retrieval_cache_key_separates_knowledge_base_scope() -> None:
    owner_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    kb_a = uuid.UUID("00000000-0000-0000-0000-000000000011")
    kb_b = uuid.UUID("00000000-0000-0000-0000-000000000022")

    key_a = retrieval_cache_key(owner_id=owner_id, knowledge_base_id=kb_a, query="same")
    key_b = retrieval_cache_key(owner_id=owner_id, knowledge_base_id=kb_b, query="same")

    assert key_a != key_b
