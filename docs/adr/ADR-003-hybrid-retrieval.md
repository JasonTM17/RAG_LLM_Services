# ADR-003: Hybrid Retrieval

## Status

Accepted. Current implementation uses hybrid vector and keyword retrieval, reciprocal rank fusion, optional reranking, and citation validation.

## Context

Learning questions may match semantic meaning, exact terms, acronyms, commands, or quoted source text. A vector-only retrieval path risks missing exact keyword evidence.

## Decision

Use hybrid retrieval with pgvector similarity, PostgreSQL Full Text Search, score fusion, optional reranking, and citation validation.

## Consequences

- Retrieval can balance semantic and lexical matches.
- Every answer must cite retrieved source IDs that passed owner scope.
- Evaluation fixtures must measure retrieval relevance and citation grounding separately.

## Alternatives Considered

- Vector-only retrieval: rejected for technical learning content.
- Keyword-only retrieval: rejected for paraphrased questions.
- External search service: deferred until local Postgres limits are measured.

## Larger-Scale Path

Tune channel weights, reranker choice, and context budgets through evaluation data before adding infrastructure. If retrieval scale exceeds Postgres limits, move lexical or vector search behind the existing retrieval interfaces and preserve deterministic citation IDs in the response contract.
