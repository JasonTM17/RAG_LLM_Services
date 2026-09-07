# ADR-005: n8n Orchestration

## Status

Accepted (2026-09-06): implementation begins with Phase 02; rationale recorded in docs/adr/ADR-007-toolchain.md context.

## Context

The platform needs scheduled and webhook-driven workflows for ingestion, synchronization, nightly evaluation, daily study tasks, and maintenance.

## Decision

Use n8n for asynchronous orchestration only. n8n must not sit inside the synchronous chat request path.

Phase 09 ships five inactive, credential-free workflow exports for document ingestion polling, scheduled knowledge sync, nightly evaluation triggering, daily study generation, and failure notification. Workflows call bounded API endpoints and record audit rows through `POST /api/v1/automation/reports`. Report writes and evaluation triggers carry idempotency keys so n8n HTTP retries do not create duplicate workflow rows; non-idempotent study generation and arbitrary external notification webhooks are not retried by n8n. The nightly evaluation workflow only creates and polls minimal evaluation run records until Phase 12 implements the evaluation runner.

## Consequences

- Chat latency and availability do not depend on n8n.
- Workflow JSON can be source-controlled and reviewed.
- Credentials must remain outside exported workflow JSON.
- API endpoints called by n8n must be bounded, authenticated, and idempotent.
- n8n metrics are enabled in Compose so Phase 10 can scrape them.
- Evaluation workflow behavior remains a trigger/status contract until the dedicated evaluation phase.

## Alternatives Considered

- Custom scheduler only: deferred because n8n gives visibility and workflow authoring.
- n8n inside chat path: rejected for latency, reliability, and failure containment.
