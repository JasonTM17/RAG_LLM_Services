# ADR-002: BGE-M3 Embeddings

## Status

Accepted (2026-09-06): implementation begins with Phase 02; rationale recorded in docs/adr/ADR-007-toolchain.md context.

## Context

DeepSeek V4 Flash is a chat model and must not be used to fake embeddings. The platform needs a separate embedding provider with a stable interface.

## Decision

Use an `EmbeddingProvider` interface with BAAI/bge-m3 as the default local embedding model.

## Consequences

- Embedding behavior is isolated from LLM provider behavior.
- Tests can use deterministic fake embeddings without paid provider calls.
- Model download and runtime resource costs must be documented before integration gates.

## Alternatives Considered

- DeepSeek chat model as embeddings: rejected.
- OpenAI embeddings: compatible future provider, not default for v1.
- Local-only random vectors: allowed only for tests, never production behavior.
