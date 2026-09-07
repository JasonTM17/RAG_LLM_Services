# RAG_LLM_Services

Production-shaped RAG, LLM, agent, automation, and observability platform for technical learning.

The target system lets a user upload learning documents, build owner-scoped knowledge bases, run hybrid retrieval, ask DeepSeek V4 Flash questions with grounded citations, generate quizzes and flashcards, and automate maintenance or evaluation workflows through n8n.

## Current Status

This repository has completed Phases 01-07: repository contract, backend foundation, document management/storage, RAG ingestion/embeddings, hybrid retrieval/reranking, the DeepSeek-compatible LLM/chat gateway, and the agent-backed study workflow layer. The FastAPI app now supports typed settings, structured redacting JSON logs, request IDs, standard error envelopes, async SQLAlchemy/Alembic, health endpoints, owner-scoped knowledge bases/documents, upload/download/delete APIs, parser/chunking/embedding ingestion, `POST /api/v1/retrieval/search`, `POST /api/v1/chat`, `POST /api/v1/chat/stream`, `POST /api/v1/study/quiz`, `POST /api/v1/study/flashcards`, and `POST /api/v1/study/learning-plan`. Async worker, frontend, full Prometheus `/metrics`, CI, deployment, live DeepSeek proof, and acceptance-demo behavior are intentionally not implemented yet.

## Architecture

The planned runtime is a Docker Compose modular monolith plus worker:

- `apps/api`: FastAPI presentation and application services.
- `apps/worker`: ingestion, embedding, evaluation, and maintenance jobs.
- `apps/web`: Next.js React TypeScript frontend.
- `packages/rag`: retrieval, chunking, and context building.
- `packages/llm`: internal model gateway and DeepSeek provider adapter.
- `packages/agents`: OpenAI Agents SDK orchestration, bounded tools, agent prompts, study outputs, context windows, and citation validation.
- `infra`: Docker, Prometheus, Grafana, and n8n provisioning.

More detail:

- [System overview](docs/architecture/system-overview.md)
- [Repository structure](docs/architecture/repository-structure.md)
- [Docker deployment notes](docs/deployment/docker.md)
- [Threat model](docs/security/threat-model.md)

## Runtime Defaults

- Python: `3.13` through `uv` (uv workspace members: `apps/api`, `packages/shared`, `packages/observability`, `packages/rag`, `packages/embeddings`, `packages/llm`, `packages/agents`).
- Node: `24.12.0` with `pnpm`.
- Local/test LLM provider: `LLM_PROVIDER=fake` so default checks never make paid API calls.
- DeepSeek OpenAI-compatible base URL: `https://api.deepseek.com`.
- Primary model alias: `deepseek-v4-flash`.
- Default LLM API mode: `responses`.
- Live DeepSeek tests: opt-in only through `RUN_DEEPSEEK_LIVE_TESTS=true`.

Local secrets live in `.env` and must not be committed. The application reads configuration from **environment variables only** — `.env` files are loaded by the runtime, not parsed in-process: `make api-run` passes `--env-file .env` to uvicorn, and compose services use `env_file`. `.env.example` documents the placeholder-only configuration surface.

AgentKit skill mirrors under `.codex/skills/`, `.claude/skills/`, `.cursor/skills/`, and `.agents/skills/` are local generated assets. They are intentionally ignored in Git; regenerate them with the project AgentKit installer/runtime if a fresh clone lacks local skills.

## Command Contract

Phase checks:

```powershell
.\scripts\verify-phase-01.ps1
.\scripts\verify-phase-02.ps1
.\scripts\verify-phase-03.ps1
.\scripts\verify-phase-04.ps1
.\scripts\verify-phase-05.ps1
.\scripts\verify-phase-06.ps1
.\scripts\verify-phase-07.ps1
```

The Makefile mirrors the same contract for environments with `make`:

```bash
make help
make plan-status
make verify-phase-01
make verify-phase-02
make verify-phase-03
make verify-phase-04
make verify-phase-05
make verify-phase-06
make verify-phase-07
make api-test      # uv run pytest -q
make api-lint      # ruff check + format check
make api-migrate   # alembic upgrade head (needs a configured Postgres)
make api-run       # uvicorn with reload on :8000
```

Health endpoints once the API is running: `GET /health/live` (process-only) and `GET /health/ready` (bounded Postgres/Redis/MinIO probes). Retrieval search is available at `POST /api/v1/retrieval/search` after documents have been indexed; mocked chat is available through `POST /api/v1/chat` and semantic SSE through `POST /api/v1/chat/stream`. Agent-backed study generation is available through `POST /api/v1/study/quiz`, `POST /api/v1/study/flashcards`, and `POST /api/v1/study/learning-plan`. Future phases will add runnable worker, web, Prometheus scrape endpoint, backup, restore, and acceptance-demo targets.

## Plan Authority

The active AgentKit plan is:

```text
plans/260906-2101-rag-llm-services-production-platform/plan.md
```

Production operating defaults are locked in:

```text
plans/260906-2101-rag-llm-services-production-platform/appendix-production-operating-model.md
```

Do not call this project production-ready until local, CI, live-provider, deployed, backup/restore, and observability gates are separately proven.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Use small Conventional Commits, stage explicit paths only, and keep secrets out of Git.
