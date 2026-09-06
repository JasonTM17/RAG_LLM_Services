# System Overview

## Overview

`RAG_LLM_Services` is planned as a Docker Compose modular monolith plus worker. The architecture keeps request handling, domain rules, RAG logic, provider adapters, automation, and observability in separate boundaries from the first implementation phase.

## Runtime Paths

Main chat path:

```text
Next.js client -> FastAPI router -> application service -> RAG or agent orchestration -> retriever -> LLM gateway -> DeepSeek adapter -> cited response
```

Ingestion path:

```text
Upload request -> metadata row -> MinIO raw object -> Redis job -> worker -> parser -> normalizer -> chunker -> embedding provider -> Postgres pgvector and FTS
```

Automation path:

```text
n8n schedule or webhook -> bounded API endpoint -> job or evaluation record -> worker -> report and metrics
```

Observability path:

```text
API, worker, exporters, and n8n -> Prometheus scrape -> Grafana dashboards
```

## Boundaries

- Presentation layer owns FastAPI routers and Next.js screens.
- Application layer owns use cases and transaction boundaries.
- Domain layer owns knowledge-base, document, conversation, citation, and evaluation rules.
- AI/RAG layer owns chunking, embeddings, retrieval, reranking, prompts, and citation validation.
- Agent layer owns OpenAI Agents SDK orchestration and bounded tool calls.
- Infrastructure layer owns database, Redis, MinIO, provider clients, and Docker wiring.
- Observability layer owns logs, metrics, dashboards, and release evidence.
- Automation layer owns n8n workflows outside the synchronous chat path.

## Production Guardrails

- Public APIs use server-resolved owner scope and do not trust client-supplied `owner_id`.
- Raw documents, raw prompts, raw chunks, secrets, and auth headers are not logged.
- Provider calls go through the internal LLM gateway.
- DeepSeek defaults to `https://api.deepseek.com`, `deepseek-v4-flash`, and Responses API mode.
- Live provider tests are opt-in and use synthetic public input only.
- Production readiness uses separate local, CI, live-provider, deployed, backup/restore, and observability gates.
