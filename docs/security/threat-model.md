# Threat Model

## Overview

This threat model covers v1 local and Docker Compose implementation. It is intentionally conservative because the system handles private documents, prompts, embeddings, conversations, provider calls, and automation workflows.

## Assets

- DeepSeek API key and future provider credentials.
- Database credentials and n8n encryption key.
- Raw uploaded documents in MinIO.
- Derived chunks, embeddings, prompts, citations, and conversations in Postgres.
- Owner-scoped knowledge bases and ingestion jobs.
- Evaluation reports generated from private data.

## Trust Boundaries

- Browser to FastAPI.
- FastAPI to Postgres, Redis, MinIO, n8n, and provider clients.
- Worker to Postgres, Redis, MinIO, embedding models, and LLM gateway.
- n8n to bounded API endpoints.
- Prometheus and Grafana to metrics endpoints.

## Primary Risks

- Cross-owner document or conversation access.
- Prompt injection from retrieved documents.
- Raw private content in logs, metrics, reports, or commits.
- Silent provider fallback changing behavior or cost.
- Duplicate ingestion creating inconsistent chunks or vectors.
- Backup that restores metadata without raw objects, or raw objects without metadata.
- Automation workflows receiving credentials or entering the synchronous chat path.

## Required Controls

- Server-resolved principal on every private query.
- Negative owner-scope tests for documents, conversations, jobs, retrieval, and citations.
- No raw document, prompt, chunk, secret, or auth-header logging.
- Internal LLM gateway for every provider call.
- Explicit fallback reason when Chat Completions is enabled.
- Idempotent ingestion keyed by checksum and document version.
- Backup/restore dry-run across Postgres, MinIO, n8n, Grafana provisioning, Prometheus config, and external secrets.
- Low-cardinality metrics with no owner IDs or private text labels.

## Release Rule

Security posture is `HOLD` until owner-scope, log redaction, prompt-injection, upload validation, rate-limit, and dependency-scan gates pass.
