# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Verified post-release

- Live DeepSeek provider smoke passed on 2026-09-08 via an operator-authorized `RUN_DEEPSEEK_LIVE_TESTS=1` run (single synthetic prompt, 16-token bound); live key containment audited with zero leaks into tracked, untracked, or git-internal artifacts.
- `v0.1.0` api, worker, and web images published to the GitHub Container Registry (automatic on `v*` tags from CI) and mirrored to Docker Hub (manifest-identical content); both registries confirmed anonymously pullable and layer-scanned clean of secrets and repository state.

### Planned

- Docker Hub CI dual-push for future tags (requires adding Docker Hub access-token repository secrets).
- Container registry publication for the observability and exporter images is out of scope; they remain upstream base images pinned by compose.
- Production authentication boundary, TLS, deployment cutover, and production backup/restore execution (all currently `HOLD` or `NOT_RUN`).

## [0.1.0] - 2026-09-08

First public release (pre-release) covering phases 01-16 of the implementation plan, tagged at `d9162f8`. The local release gate `scripts/verify-phase-16.ps1` passes (`303 passed, 1 skipped`); hosted GitHub Actions (CI, Security, Container Build) are green on the tagged commit. Live-provider, registry, deployment, and production evidence remain unobserved.

### Added

- Define the repository contract, platform ADRs, and pinned Python 3.13 `uv` workspace toolchain.
- Add the FastAPI backend foundation with health endpoints, async SQLAlchemy models, and Alembic migrations.
- Add owner-scoped knowledge-base and document APIs with MinIO raw-object storage.
- Add the RAG ingestion pipeline: parsing, normalization, semantic chunking, BGE-M3 embeddings, and version-aware pgvector indexing.
- Add hybrid vector-plus-keyword retrieval with optional reranking and source-labeled context building.
- Add a provider-neutral LLM gateway with a DeepSeek-compatible adapter; chat defaults to the deterministic mocked provider.
- Add study agent endpoints for quizzes, flashcards, and learning plans with citation validation.
- Add the Redis/Celery worker path for asynchronous ingestion and evaluation jobs.
- Add source-controlled n8n automation contracts and five workflow exports under `workflows/n8n/`.
- Add Prometheus metrics for API and worker surfaces with structured redacting JSON logs and request IDs.
- Add source-provisioned Grafana datasources and dashboards.
- Add a fixture-safe RAG evaluation runner with deterministic retrieval and citation metrics and a queued evaluation API.
- Add the Next.js operational frontend for chat, documents, knowledge bases, study tools, and system status.
- Add security hardening gates for CORS, rate limits, upload abuse, prompt injection, citation abuse, SQL parameterization, dependency advisories, and secret-shaped values.
- Add GitHub Actions workflow definitions, documentation, ADRs, and developer `make` targets, validated locally.
- Add release-readiness evidence with residual release gates and rollback notes.

### Fixed

- Reclaim stale ingestion jobs and evaluation runs so a crashed worker cannot leave them stuck in `RUNNING`.
- Preserve punctuation, heading hierarchy, and parser edge cases during chunking.
- Fix document storage key traceability, unicode downloads, and object cleanup.
- Propagate request IDs on 500 responses, harden logging state access, and redact secret prefixes.
- Harden release Compose topology and migration steps.
