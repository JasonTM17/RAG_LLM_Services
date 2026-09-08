# Hybrid Retrieval and Reranking Pipeline

## Overview

The retrieval engine fuses semantic dense retrieval with lexical full-text search through Reciprocal Rank Fusion, optional reranking, and bounded source-labeled context selection. It consumes only indexed current-version chunks produced by the [ingestion pipeline](ingestion-pipeline.md).

## Pipeline Architecture

```text
POST /api/v1/retrieval/search
  │
  ▼
RetrievalService
  │
  ├──► QueryNormalizer (NFC normalization, control char stripping, quote balancing)
  │
  ├──► VectorRetriever (dense embedding via BGE-M3/Fake, pgvector <=> search)
  │
  ├──► KeywordRetriever (lexical FTS query, GIN index on to_tsvector('english', content))
  │
  ├──► ReciprocalRankFusion (score = sum(w / (k + rank)), deterministic tie-breaking)
  │
  ├──► RerankerProvider (BGE-Reranker-v2-m3 cross-encoder or Fake/Null pass-through)
  │
  ├──► ContextBuilder (citation tags [S1], [S2]..., metadata header, token budget enforcement)
  │
  ├──► RagQueryRepository (records audit event in rag_queries table)
  │
  ├──► Retrieval metrics (query counter, stage latency, per-channel latency, chunk count)
  │
  ▼
RetrievalSearchResponse (JSON with ranked hits and bounded ContextBundle)
```

## Key Components

### 1. Domain Types (`packages/rag/src/rag_llm_services_rag/retrieval/types.py`)

- `RetrievalMethod`: Enum `VECTOR`, `KEYWORD`, `HYBRID`.
- `CandidateChunk`: Search hit before fusion/reranking.
- `RetrievalResult`: Ranked result produced by fusion or reranking.
- `CitedChunk`: Chunk selected for the context bundle, tagged with `[S1]`, `[S2]`, etc.
- `ContextBundle`: Token-bounded context formatted with citation headers.
- `RetrievalFilter`: Multi-tenant filtering by `knowledge_base_id`, `document_ids`, `mime_types`, `page`, `section`, `created_after`, `created_before`, and allowlisted metadata values.

### 2. Query Normalizer (`packages/rag/src/rag_llm_services_rag/retrieval/query.py`)

- Strips ASCII control characters (`[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]`).
- Performs Unicode NFC normalization to preserve Vietnamese diacritics and CJK characters.
- Balances double-quotes to prevent syntax errors in `websearch_to_tsquery`.
- Collapses redundant whitespace.

### 3. Vector Retrieval (`packages/rag/src/rag_llm_services_rag/retrieval/vector.py`)

- Embeds queries via `EmbeddingProvider.embed_query`.
- On PostgreSQL: utilizes pgvector's cosine distance `<=>` with HNSW index `ix_document_chunks_embedding_hnsw`.
- On SQLite / offline test: utilizes mathematical cosine similarity calculation.
- Scoped strictly to `owner_id`, `DocumentStatus.INDEXED`, and the document's current version for multi-tenant isolation and stale-chunk exclusion.

### 4. Keyword Retrieval (`packages/rag/src/rag_llm_services_rag/retrieval/keyword.py`)

- On PostgreSQL: utilizes `websearch_to_tsquery('english', query)` against `to_tsvector('english', content)` accelerated by GIN index `ix_document_chunks_content_tsv`.
- Ranked via `ts_rank_cd`.
- On SQLite / offline test: lexical token frequency matching.
- Scoped strictly to `owner_id`, `DocumentStatus.INDEXED`, and the document's current version for multi-tenant isolation and stale-chunk exclusion.

### 5. Reciprocal Rank Fusion (`packages/rag/src/rag_llm_services_rag/retrieval/fusion.py`)

- Formula: $RRF\_score = \sum_{m} \frac{w_m}{k + rank_m}$
- Default smoothing constant $k = 60$.
- Configurable channel weights (e.g. `vector_weight = 1.0`, `keyword_weight = 1.0`).
- Runtime defaults are configured through `RAG_VECTOR_TOP_K`, `RAG_KEYWORD_TOP_K`, `RAG_RERANK_TOP_K`, `RAG_RRF_K`, `RAG_RRF_VECTOR_WEIGHT`, `RAG_RRF_KEYWORD_WEIGHT`, and `RAG_CONTEXT_TOKEN_BUDGET`.
- Deterministic tie-breaking by `(-score, str(chunk_id))`.
- Chunks present in both channels are attributed to `RetrievalMethod.HYBRID`.

### 6. Reranking (`packages/rag/src/rag_llm_services_rag/retrieval/reranker.py`)

- Interface: `RerankerProvider` protocol.
- Implementations:
  - `BGERerankerProvider`: process-scoped cross-encoder (`BAAI/bge-reranker-v2-m3`), offloading CPU inference via `asyncio.to_thread`.
  - `FakeRerankerProvider`: deterministic lexical scoring for testing.
  - `NullRerankerProvider`: pass-through when reranking is disabled (`RERANKER_PROVIDER=none`).

### 7. Context Builder (`packages/rag/src/rag_llm_services_rag/retrieval/context.py`)

- Assigns sequential citation tags `[S1]`, `[S2]`, ..., `[SN]`.
- Formats citation headers: `[S1] Source: report.pdf (Page 2, Section: Architecture)`.
- Strictly enforces `max_token_budget` (default 6000 tokens) using multilingual token estimator.

### 8. Audit & Observability

Primary files:

- `apps/api/src/rag_llm_services_api/db/models/rag_query.py`
- `packages/observability/src/rag_llm_services_observability/metrics.py`

- Persists retrieval query events to `rag_queries` table.
- Records total latency, per-stage `stage_latencies_ms`, result count, selected chunk IDs, and filters.
- Records `rag_queries_total` by bounded `method` label.
- Records `rag_retrieval_duration_seconds` by bounded `stage` label (`normalize`, `vector`, `keyword`, `fusion`, `rerank`, `context`, `total`).
- Records `rag_vector_search_duration_seconds`, `rag_keyword_search_duration_seconds`, `rag_rerank_duration_seconds`, and `rag_retrieved_chunks` for Prometheus scrape.
- Avoids high-cardinality metric labels; labels do not contain query text, owner IDs, request IDs, document IDs, chunk IDs, or knowledge-base IDs.

## API Endpoints

- `POST /api/v1/retrieval/search`:
  - Request body: `RetrievalSearchRequest`
  - Authentication: `X-User-Id` header (in development/test) or bearer token.
  - Response: `RetrievalSearchResponse` containing ranked chunks, `ContextBundle`, total latency, and per-stage latency.

## Evaluation Framework

The fixture-safe evaluation path can run without paid provider calls:

- Baseline dataset: `evals/datasets/baseline-learning-rag.jsonl`.
- Dataset fields: `question`, `expected_answer`, `expected_sources`,
  `metadata`, plus optional fixture `retrieved_sources` and deterministic
  `answer`.
- Metrics: retrieval hit rate, Recall@K, MRR, nDCG@K, context relevance,
  answer relevance, citation correctness, citation recall, citation precision,
  missing citation count, and faithfulness.
- Thresholds: configured through `EVAL_*_THRESHOLD` variables plus
  `EVAL_TOP_K`; threshold misses are explicit `FAIL` results.
- CLI: `uv run python scripts/run-eval.py` or `make eval` where `make` is
  available.
- API: `POST /api/v1/evaluations` creates an idempotent `PENDING` run and
  enqueues a worker task; the worker marks `RUNNING`, executes the
  deterministic evaluation, stores aggregate results in
  `evaluation_runs.metadata_json.result`, and writes a safe report under
  `EVAL_REPORTS_DIR`. `GET /api/v1/evaluations/{run_id}` returns the current
  status and aggregate result when available.

Generated reports summarize metrics, thresholds, expected source IDs, retrieved
source IDs, and fixture metadata only; they do not include raw questions,
expected answers, model answers, or retrieved document text.

## Verification

- `.\scripts\verify-phase-05.ps1` passes with `PHASE_05_VERIFY_PASS`.
- The Phase 05 gate covers import smoke, Alembic history, ruff check/format, mypy, the full pytest suite, secret scan, `git diff --check`, retrieval filtering, tenant isolation, reranker disabling, audit rows, and low-cardinality metric labels.
- Live PostgreSQL `EXPLAIN` for pgvector/GIN query plans is deferred until a live Postgres environment is available.
- `.\scripts\verify-phase-12.ps1` covers the evaluation runner, config parity,
  unit metric tests, API integration tests, generated report secret scan, full
  lint/typecheck/test gates, and `git diff --check`.
