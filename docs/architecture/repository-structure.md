# Repository Structure

## Overview

The repository is organized around deployable applications, reusable packages, infrastructure assets, tests, docs, scripts, and AgentKit plans.

## Layout

```text
apps/
  api/       FastAPI app and HTTP presentation boundary.
  worker/    Background worker for ingestion, evaluation, and maintenance.
  web/       Next.js React TypeScript frontend.
packages/
  agents/   OpenAI Agents SDK orchestration and tool definitions.
  embeddings/ Embedding provider abstractions and implementations.
  llm/      Internal model gateway and provider adapters.
  observability/ Logging, metrics, tracing, and evidence helpers.
  rag/      Chunking, retrieval, reranking, context building, citations.
  shared/   Cross-application types, errors, and utilities.
infra/
  docker/   Compose and container runtime assets.
  prometheus/ Prometheus config and alerting assets.
  grafana/  Provisioned datasources and dashboards.
  n8n/      n8n provisioning notes and safe import assets.
workflows/n8n/ Source-controlled n8n workflow JSON.
evals/       Evaluation fixtures, reports, and local private outputs.
tests/       Unit, integration, and end-to-end tests.
docs/        Architecture, deployment, security, and ADR docs.
scripts/     Developer and release utility scripts.
plans/       AgentKit implementation plans and evidence.
```

## Rules

- Routers must not call SQL directly.
- Routers must not construct prompts directly.
- Agents must use bounded application tools instead of direct database access.
- Business logic must not depend on FastAPI.
- RAG behavior must not live in one large file.
- Infrastructure clients must remain behind package or application-service boundaries.
