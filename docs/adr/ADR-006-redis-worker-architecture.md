# ADR-006: Redis Worker Architecture

## Status

Proposed

## Context

Document parsing, chunking, embedding, evaluation, and maintenance can be slow or retryable. The API should accept work quickly and process it outside the request path.

## Decision

Use Redis-backed background work for v1, with the exact Python worker framework selected during implementation and recorded before Phase 08 completes.

## Consequences

- Upload requests return metadata and job IDs without waiting for full ingestion.
- Worker jobs must be idempotent and version-aware.
- Queue depth and job lifecycle metrics become release evidence.
- Framework choice must be justified against FastAPI integration, retries, scheduling, Windows developer ergonomics, and Docker Compose operations.

## Alternatives Considered

- Synchronous ingestion: rejected for latency and resilience.
- Kubernetes-native job system: out of scope for v1.
- Database polling only: reserved as a fallback if Redis worker complexity outweighs benefits.
