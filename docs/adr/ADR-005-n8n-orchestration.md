# ADR-005: n8n Orchestration

## Status

Accepted. Current implementation uses n8n for asynchronous orchestration and keeps chat served directly by the API and LLM gateway.

## Context

The platform needs scheduled and webhook-driven workflows for ingestion, synchronization, nightly evaluation, daily study tasks, and maintenance.

## Decision

Use n8n for asynchronous orchestration only. n8n must not sit inside the synchronous chat request path.

The repository ships five inactive, credential-free workflow exports for document ingestion polling, scheduled knowledge sync, nightly evaluation triggering, daily study generation, and failure notification. Workflows call bounded API endpoints and record audit rows through `POST /api/v1/automation/reports`. Report writes and evaluation triggers carry idempotency keys so n8n HTTP retries do not create duplicate workflow rows; non-idempotent study generation and arbitrary external notification webhooks are not retried by n8n. Nightly evaluation creates queued evaluation runs and records the current status/result.

## Consequences

- Chat latency and availability do not depend on n8n.
- Workflow JSON can be source-controlled and reviewed.
- Credentials must remain outside exported workflow JSON.
- API endpoints called by n8n must be bounded, authenticated, and idempotent.
- n8n metrics are enabled in Compose so Phase 10 can scrape them.
- Evaluation workflow behavior remains a trigger/status/report contract over the queued evaluation API.

## Alternatives Considered

- Custom scheduler only: deferred because n8n gives visibility and workflow authoring.
- n8n inside chat path: rejected for latency, reliability, and failure containment.

## Larger-Scale Path

Move to n8n queue mode, external credentials, and dedicated workflow ownership only after production auth and secrets management are in place. If workflows become mission-critical, add replay/idempotency audits and consider a code-owned scheduler for paths that need stricter deploy-time review than visual workflow editing provides.
