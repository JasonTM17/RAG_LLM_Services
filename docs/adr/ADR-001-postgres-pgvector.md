# ADR-001: PostgreSQL and pgvector

## Status

Accepted. Current implementation uses PostgreSQL, pgvector, and PostgreSQL Full Text Search for the v1 storage and retrieval core.

## Context

The platform needs transactional metadata, owner-scoped document state, conversations, evaluation rows, keyword retrieval, and vector retrieval.

## Decision

Use PostgreSQL as the primary database and pgvector for embedding storage. Use PostgreSQL Full Text Search for keyword retrieval.

## Consequences

- One operational database handles metadata, text search, and vectors for v1.
- Hybrid retrieval can combine vector similarity and keyword ranking without a separate search cluster.
- Future scale limits must be measured before introducing Elasticsearch, OpenSearch, or a dedicated vector database.

## Alternatives Considered

- Dedicated vector database: deferred until scale requires it.
- SQLite: rejected for production-shaped local architecture with pgvector and worker concurrency.
- Search cluster first: deferred to avoid extra operational burden in v1.

## Larger-Scale Path

Measure query latency, index size, recall, and operational load before splitting storage. If Postgres becomes the bottleneck, introduce a dedicated search or vector service behind the retrieval interfaces while keeping owner scope, current-version filtering, and citation validation unchanged.
