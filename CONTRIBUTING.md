# Contributing

## Getting Started

Prerequisites:

- Git.
- `uv` with Python 3.13 (pinned in `.python-version`).
- `make` is optional. The Makefile pins `SHELL := powershell`, so Windows users without `make` run the phase verifier directly, for example `pwsh -File scripts/verify-phase-01.ps1`.
- Docker Desktop when you need the compose services: `postgres`, `redis`, `minio`, `minio-create-bucket`, and `n8n` start by default; `api`, `worker`, `web`, and observability are opt-in through Compose profiles. See `docs/deployment/docker.md`.
- Node.js with pnpm for the frontend commands (`make web-*`); the README records the pinned versions.

Common commands:

| Command | What it does |
| --- | --- |
| `uv sync` | Install the Python workspace. |
| `make api-test` | Full pytest suite (`uv run pytest -q`). |
| `make api-lint` | `ruff check` plus `ruff format --check`. |
| `make api-typecheck` | mypy over `apps/api/src`, `apps/worker/src`, and `packages`. |
| `make verify-phase-NN` | Run `scripts/verify-phase-NN.ps1` for the phase you touched. |
| `make api-migrate` | Apply Alembic migrations (`uv run alembic -c apps/api/alembic.ini upgrade head`). |
| `make api-run` | Start the API on the host with uvicorn, `--reload`, and `--env-file .env`. |
| `make worker-run` | Start the Celery ingestion worker on `INGESTION_QUEUE_NAME`. |

Configuration:

- Copy `.env.example` to `.env` and replace the `replace-with-*` placeholders with local values.
- The application reads environment variables only. `.env` is loaded by the runtime (`make api-run` passes `--env-file .env` to uvicorn; Docker Compose supplies service environments), not in-process.
- `LLM_PROVIDER=fake` and `RUN_DEEPSEEK_LIVE_TESTS=false` keep local runs and tests free of paid provider calls.

## Workflow

1. Inspect repository state before editing.
2. Work from the active AgentKit plan under `plans/`.
3. Keep each change aligned to the current phase exit criterion.
4. Run the narrow verification command for the phase.
5. Stage explicit paths only.
6. Commit small logical units with Conventional Commits.
7. Treat hosted CI, live-provider, deploy, and production evidence as separate claims.

AgentKit contracts, runtime config, hooks, agents, plans, and documentation are source. Generated local skill mirrors under `.codex/skills/`, `.claude/skills/`, `.cursor/skills/`, and `.agents/skills/` are not source for this product repository; regenerate them locally when needed instead of staging them.

## Commit Style

Allowed prefixes:

- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `docs:`
- `chore:`
- `ci:`
- `perf:`
- `security:`

Use an optional scope naming the touched area, as in `feat(rag):`, `fix(api):`, or `feat(worker):`. Documentation-only changes use `docs:`. Do not force push. Do not combine unrelated feature, config, and documentation changes into one commit when they can be reviewed separately.

## Secret Policy

- Real secrets belong in `.env` or an external secret store.
- `.env.example` must contain placeholders only.
- Never commit API keys, passwords, auth headers, raw private documents, raw prompts, or provider error bodies that expose sensitive data.
- Before commit, run a credential-shaped scan that excludes `.env`.

## Verification Commands

Use the smallest gate that covers the change:

- CI workflow definitions: `make validate-workflows`.
- Documentation, ADR shape, and repo-relative links: `make docs-check`.
- API/backend behavior: `make api-lint`, `make api-typecheck`, and `make api-test`.
- Frontend behavior: `make web-verify` and `make web-build`.
- n8n, Prometheus, and Grafana contracts: `make validate-n8n`, `make validate-prometheus`, and `make validate-grafana`.
- Security-sensitive changes: `make secret-scan`, `make sql-scan`, and `make dependency-scan`.
- Phase verification: `make verify-phase-NN` per phase; `make verify-phase-16` is the release readiness gate.

Build application images before claiming container readiness:

```powershell
make container-build
```

## Documentation Expectations

- Keep `docs/` current when behavior, commands, contracts, or operator expectations change.
- Document material architecture decisions as ADRs under `docs/adr/`.
- Reference files by repository-relative paths; do not embed machine-specific absolute paths.
- Validate documentation paths, links, and ADR shape with `make docs-check` before commit.

## Evidence Policy

Report evidence using the narrowest truthful status:

- `LOCAL_PASS`
- `CI_PASS`
- `LIVE_PROVIDER_PASS`
- `DEPLOYED_PASS`
- `HOLD`
- `NOT_RUN`

Local checks do not prove CI, deployment, live provider behavior, backup restore, or production readiness.

Each phase records its verification results under `plans/260906-2101-rag-llm-services-production-platform/` before the phase is declared complete. Never weaken a verification gate or change an oracle to make a failing check pass; fix the defect or report `HOLD` or `NOT_RUN` truthfully.
