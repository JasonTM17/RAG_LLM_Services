# ADR-005: n8n Orchestration

## Status

Proposed

## Context

The platform needs scheduled and webhook-driven workflows for ingestion, synchronization, nightly evaluation, daily study tasks, and maintenance.

## Decision

Use n8n for asynchronous orchestration only. n8n must not sit inside the synchronous chat request path.

## Consequences

- Chat latency and availability do not depend on n8n.
- Workflow JSON can be source-controlled and reviewed.
- Credentials must remain outside exported workflow JSON.
- API endpoints called by n8n must be bounded, authenticated, and idempotent.

## Alternatives Considered

- Custom scheduler only: deferred because n8n gives visibility and workflow authoring.
- n8n inside chat path: rejected for latency, reliability, and failure containment.
