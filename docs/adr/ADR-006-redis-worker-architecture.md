# ADR-006: Redis Worker Architecture

## Status

Accepted (2026-09-07): Phase 08 selects Celery with Redis broker/result backend.

## Context

Document parsing, chunking, embedding, evaluation, and maintenance can be slow or retryable. The API should accept work quickly and process it outside the request path.

## Decision

Use Celery 5.x with Redis as broker and result backend for v1 asynchronous ingestion. API routes publish typed ingestion payloads through a small queue port, while `apps/worker` owns task execution and calls the existing ingestion pipeline outside the request path.

Default in-process settings use a memory queue for tests and offline local imports. Compose and production configuration use `QUEUE_PROVIDER=celery`; production settings fail closed if the memory queue is selected.

## Consequences

- Upload requests return metadata, job IDs, and queue task IDs without parsing or embedding in the request.
- Worker jobs are version-aware and safe to retry because chunk replacement is idempotent.
- Celery supplies mature retry/backoff controls, JSON serialization, queue routing, Redis visibility timeout support, and familiar Docker Compose operations.
- Queue depth and job lifecycle metrics become release evidence.
- The API remains decoupled from Celery primitives through the queue port.

## Alternatives Considered

- Synchronous ingestion: rejected for latency and resilience.
- Kubernetes-native job system: out of scope for v1.
- Database polling only: reserved as a fallback if Redis worker complexity outweighs benefits.
- Bare asyncio worker: rejected for v1 because retry/backoff, durable broker integration, and operator familiarity would need more project-owned code.

## References

- Celery task retry guide: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- Celery Redis broker/backend guide: https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html
- Celery configuration guide: https://docs.celeryq.dev/en/stable/userguide/configuration.html
