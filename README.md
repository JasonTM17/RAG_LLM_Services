# RAG_LLM_Services

Production-shaped RAG, LLM, agent, automation, and observability platform for technical learning.

The target system lets a user upload learning documents, build owner-scoped knowledge bases, run hybrid retrieval, ask DeepSeek V4 Flash questions with grounded citations, generate quizzes and flashcards, and automate maintenance or evaluation workflows through n8n.

## Current Status

This repository has completed Phases 01-13: repository contract, backend foundation, document management/storage, RAG ingestion/embeddings, hybrid retrieval/reranking, the DeepSeek-compatible LLM/chat gateway, the agent-backed study workflow layer, Redis/Celery async ingestion infrastructure, n8n automation workflow contracts, Prometheus observability, Grafana dashboards, the fixture-safe RAG evaluation framework, and the Next.js frontend application. The FastAPI app now supports typed settings, structured redacting JSON logs, request IDs, standard error envelopes, async SQLAlchemy/Alembic, health endpoints, `GET /metrics`, owner-scoped knowledge bases/documents, upload/download/delete APIs with current-version chunk counts, queued document ingestion, job status/queue status APIs, parser/chunking/embedding ingestion, `POST /api/v1/retrieval/search`, `POST /api/v1/chat`, `POST /api/v1/chat/stream` with final-event citations, `POST /api/v1/study/quiz`, `POST /api/v1/study/flashcards`, `POST /api/v1/study/learning-plan`, `POST /api/v1/automation/reports`, queued deterministic `POST /api/v1/evaluations`, and `GET /api/v1/evaluations/{run_id}` with safe aggregate results after the worker completes. The compose stack includes a web profile, n8n with persistent storage and metrics enabled, a worker metrics endpoint, Prometheus scrape configuration, Grafana datasource/dashboard provisioning, Redis/Postgres exporters, and optional cAdvisor. CI, deployment, live DeepSeek proof, and acceptance-demo behavior are intentionally not implemented yet.

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

- Python: `3.13` through `uv` (uv workspace members: `apps/api`, `apps/worker`, `packages/shared`, `packages/observability`, `packages/rag`, `packages/embeddings`, `packages/llm`, `packages/agents`).
- Node: `24.12.0` with `pnpm@11.0.9`.
- Local/test LLM provider: `LLM_PROVIDER=fake` so default checks never make paid API calls.
- DeepSeek OpenAI-compatible base URL: `https://api.deepseek.com`.
- Primary model alias: `deepseek-v4-flash`.
- Default LLM API mode: `responses`.
- Live DeepSeek tests: opt-in only through `RUN_DEEPSEEK_LIVE_TESTS=true`.
- Compose worker queue: `QUEUE_PROVIDER=celery`, Redis broker/result backend, `INGESTION_QUEUE_NAME=ingestion`, and `WORKER_POOL=threads` so worker task metrics share the scraped process registry; `WORKER_METRICS_HOST_PORT` can change the host bind while Prometheus keeps scraping `worker:9108`.
- Compose n8n image: `docker.n8n.io/n8nio/n8n:2.37.11`, overridable with `N8N_IMAGE`.
- n8n workflow API base from the container: `RAG_API_BASE_URL=http://host.docker.internal:8000/api/v1`.
- Prometheus image: `prom/prometheus:v2.55.1`, scraping API `GET /metrics`, worker `GET /metrics`, n8n, Postgres exporter, Redis exporter, and optional cAdvisor.
- Grafana image: `grafana/grafana:13.2.1`, with Prometheus datasource and dashboards provisioned from `infra/grafana/`.
- Evaluation defaults: `EVAL_DATASET_PATH=evals/datasets/baseline-learning-rag.jsonl`, `EVAL_REPORTS_DIR=evals/reports/local`, `EVAL_TOP_K=5`, and threshold variables under `EVAL_*_THRESHOLD`. Default evaluation uses fixture data and deterministic metrics only.
- Frontend defaults: `RAG_BACKEND_ORIGIN=http://localhost:8000` for Next.js server-side rewrites, `WEB_PORT=3001` for the compose web profile, and `WEB_E2E_PORT=43117` for Playwright. Browser code calls same-origin `/api/v1/*` and `/health/*` routes only.

Local secrets live in `.env` and must not be committed. The application reads configuration from **environment variables only** — `.env` files are loaded by the runtime, not parsed in-process: `make api-run` passes `--env-file .env` to uvicorn, and Compose reads `.env` for variable substitution into service environments. `.env.example` documents the placeholder-only configuration surface.

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
.\scripts\verify-phase-08.ps1
.\scripts\verify-phase-09.ps1
.\scripts\verify-phase-10.ps1
.\scripts\verify-phase-11.ps1
.\scripts\verify-phase-12.ps1
.\scripts\verify-phase-13.ps1
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
make verify-phase-08
make verify-phase-09
make verify-phase-10
make verify-phase-11
make verify-phase-12
make verify-phase-13
make eval
make validate-n8n
make validate-prometheus
make validate-grafana
make web-dev
make web-verify
make web-e2e
make api-test      # uv run pytest -q
make api-lint      # ruff check + format check
make api-migrate   # alembic upgrade head (needs a configured Postgres)
make api-run       # uvicorn with reload on :8000
make worker-run    # celery ingestion worker for the configured queue
```

Health endpoints once the API is running: `GET /health/live` (process-only), `GET /health/ready` (bounded Postgres/Redis/Celery broker/MinIO probes), and `GET /metrics` (Prometheus text exposition with no external provider calls). Retrieval search is available at `POST /api/v1/retrieval/search` after documents have been indexed; mocked chat is available through `POST /api/v1/chat` and semantic SSE through `POST /api/v1/chat/stream`. Agent-backed study generation is available through `POST /api/v1/study/quiz`, `POST /api/v1/study/flashcards`, and `POST /api/v1/study/learning-plan`. n8n automation contracts are available through `workflows/n8n/`, `POST /api/v1/automation/reports`, and `POST/GET /api/v1/evaluations`; local evaluation is also available through `make eval` or `uv run python scripts/run-eval.py`. Grafana provisioning lives under `infra/grafana/` and loads dashboards from source control. Future phases will add backup, restore, acceptance-demo, CI, deployment, and release targets.

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
