# Docker Deployment Notes

## Overview

V1 targets Docker Compose, not Kubernetes. Compose is used for local development, integration testing, observability proof, and future deployment rehearsal.

## Planned Services

- `api`: FastAPI application.
- `worker`: background ingestion and evaluation worker.
- `web`: Next.js frontend.
- `postgres`: PostgreSQL with pgvector.
- `redis`: queue and cache.
- `minio`: raw private document object storage.
- `n8n`: asynchronous automation.
- `prometheus`: metrics scrape target.
- `grafana`: provisioned dashboards.

## Environment

Use `.env` for local runtime secrets and `.env.example` for placeholders. Do not bake secrets into images or committed compose files.

The worker service receives the `EVAL_*` variables used by the Phase 12
evaluation runner, including dataset path, report directory, top K, and
thresholds. Evaluation tasks share the configured Celery/Redis queue with
ingestion tasks and write generated reports to the mounted project workspace.

The web service receives `RAG_BACKEND_ORIGIN`, which is consumed only by
Next.js server-side rewrites. Browser code uses same-origin `/api/v1/*` and
`/health/*` requests, so provider keys and backend credentials are not exposed
through `NEXT_PUBLIC_*` variables. The compose web profile defaults to
`WEB_PORT=3001` on the host to avoid Grafana's default `3000` port.

API rate limiting is configured with `RATE_LIMIT_*`. Direct local/test imports
default to an in-memory limiter so tests run offline, while `.env.example` sets
`RATE_LIMIT_BACKEND=redis` for Compose and production-shaped runs. Production
mode fails closed if rate limiting is disabled or not backed by Redis.

## Readiness Gates

- Compose config validates.
- Database migrations apply.
- API liveness and readiness endpoints pass.
- Worker starts and drains fixture ingestion jobs.
- Prometheus can scrape API and worker metrics.
- Grafana datasource and dashboards provision from source-controlled files.
- n8n workflows import without credentials.
- Web app lint, type-check, unit/component tests, build, and mocked Playwright
  desktop/mobile flow pass.
- Security verifier passes: prompt-injection, upload abuse, citation abuse,
  secret/logging scan, SQL parameterization scan, dependency scan, and affected
  API tests.

## n8n

`docker-compose.yml` includes an `n8n` service backed by the `n8n_data` volume. It is configured through `.env` substitution, enables `N8N_METRICS`, and receives only runtime environment variables, not exported credentials. Workflow JSON lives under `workflows/n8n/` and must pass `uv run python scripts/validate-n8n-workflows.py` before commit.

## Prometheus

`docker-compose.yml` includes an observability profile with Prometheus,
Grafana, Postgres exporter, and Redis exporter. Prometheus scrapes the API at
`host.docker.internal:8000`, the worker at `worker:9108`, n8n at `n8n:5678`,
and the exporter services through the compose network. Worker metrics are
enabled by `WORKER_METRICS_ENABLED=true` in the compose environment and remain
off by default for direct Python imports and tests. The compose worker defaults
to `WORKER_POOL=threads` with bounded `WORKER_CONCURRENCY=4` so Celery task
updates and the worker `/metrics` endpoint share the same in-process metric
registry. The worker listens on port `9108` inside the compose network for the
Prometheus target; `WORKER_METRICS_HOST_PORT` only changes the host bind port.

Validate the scrape contract with:

```powershell
uv run python scripts/validate-prometheus-config.py
docker compose --profile worker --profile observability config --quiet
```

Container metrics are optional and use the `container-observability` profile.

## Grafana

Grafana runs in the observability profile and provisions Prometheus plus the
RAG dashboards from source-controlled files under `infra/grafana/`. Start it
with:

```powershell
docker compose --profile worker --profile observability up
```

Open `http://localhost:${GRAFANA_PORT:-3000}`. The `.env.example` admin
password is a local placeholder; set a real `GRAFANA_ADMIN_PASSWORD` in `.env`
or secret-backed production environment before starting Grafana.

Validate the dashboard contract with:

```powershell
uv run python scripts/validate-grafana-dashboards.py
```

## Web

Start the Next.js frontend in the `web` profile:

```powershell
docker compose --profile web up web
```

Open `http://localhost:${WEB_PORT:-3001}`. For direct local development, run
`make api-run` in one terminal and `pnpm web:dev` in another; the dev server
uses port `3000` unless overridden by Next.js CLI flags.

## Non-Goals

- Kubernetes manifests.
- Managed cloud deployment.
- Production cutover.
- Public internet SLO claims before deployed measurements exist.
