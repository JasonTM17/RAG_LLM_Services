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

## Readiness Gates

- Compose config validates.
- Database migrations apply.
- API liveness and readiness endpoints pass.
- Worker starts and drains fixture ingestion jobs.
- Prometheus can scrape API and worker metrics.
- Grafana datasource and dashboards provision from source-controlled files.
- n8n workflows import without credentials.

## n8n

`docker-compose.yml` includes an `n8n` service backed by the `n8n_data` volume. It is configured through `.env` substitution, enables `N8N_METRICS`, and receives only runtime environment variables, not exported credentials. Workflow JSON lives under `workflows/n8n/` and must pass `uv run python scripts/validate-n8n-workflows.py` before commit.

## Prometheus

`docker-compose.yml` includes an observability profile with Prometheus,
Postgres exporter, and Redis exporter. Prometheus scrapes the API at
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

## Non-Goals

- Kubernetes manifests.
- Managed cloud deployment.
- Production cutover.
- Public internet SLO claims before deployed measurements exist.
