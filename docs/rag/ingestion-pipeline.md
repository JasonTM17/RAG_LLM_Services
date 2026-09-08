# Ingestion Pipeline

## Purpose

The ingestion pipeline turns an owner-scoped uploaded document into current, citeable chunks. It is deliberately outside the chat request path so large parsing, chunking, and embedding work can be retried without blocking users.

## Owners

- API upload and document lifecycle: `apps/api/src/rag_llm_services_api/application/document_service.py`.
- Queue publication and status: `apps/api/src/rag_llm_services_api/infrastructure/queue/`.
- Worker entry points: `apps/worker/src/rag_llm_services_worker/`.
- Parser, normalization, chunking, and retrieval-ready context types: `packages/rag/src/rag_llm_services_rag/`.
- Embedding provider boundary: `packages/embeddings/src/rag_llm_services_embeddings/`.

## Flow

```text
document upload
  -> owner-scoped metadata row
  -> raw object in MinIO
  -> Redis/Celery ingestion job
  -> worker parser and normalizer
  -> semantic chunker
  -> embedding provider
  -> current-version chunks in Postgres and pgvector
```

## Design Constraints

- Owner scope is resolved server-side and must survive every API, queue, and worker boundary.
- Re-indexing replaces chunks for the current document version, so retries do not append duplicate citeable context.
- Parser output is source data, not instructions. Chat and agent prompts wrap retrieved content as untrusted context before model calls.
- The default test and CI path uses deterministic local providers. Live provider behavior is a separate opt-in gate.
- Raw documents and raw chunk text are not valid log or metric labels.

## Verification

- Ingestion behavior: `tests/integration/rag/test_ingestion_pipeline.py`.
- Worker behavior: `tests/integration/worker/test_ingestion_task.py`.
- Upload validation: `tests/unit/documents/test_upload_validation.py` and `tests/security/test_upload_abuse.py`.
- Full local gate: `.\scripts\verify-phase-15.ps1`.
