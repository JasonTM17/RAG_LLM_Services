# ADR-002: BGE-M3 Embeddings

## Status

Accepted. Current implementation uses an embedding provider boundary with BGE-M3 as the production-shaped default and deterministic fake embeddings for tests.

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

## Larger-Scale Path

Add provider-specific adapters only behind the `EmbeddingProvider` interface. Compare candidate models through the fixture evaluation path and a larger offline benchmark before changing defaults, and keep model downloads, GPU placement, and cold-start cost out of the synchronous API path.
