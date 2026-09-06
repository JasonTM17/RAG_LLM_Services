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

## Non-Goals

- Kubernetes manifests.
- Managed cloud deployment.
- Production cutover.
- Public internet SLO claims before deployed measurements exist.
