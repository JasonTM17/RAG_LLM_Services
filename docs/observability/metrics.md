# Metrics and Observability

The platform exposes Prometheus-compatible metrics for the API, worker, RAG
pipeline, LLM calls, ingestion, cache counters, and backing services. Grafana
provisioning is source-controlled so local dashboards load without manual
imports.

## Endpoints

- API metrics: `GET /metrics` on the FastAPI service.
- Worker metrics: `GET /metrics` on `WORKER_METRICS_PORT` when
  `WORKER_METRICS_ENABLED=true`.
- n8n metrics: `GET /metrics` on the n8n service when `N8N_METRICS=true`.
- Postgres and Redis metrics are exposed by the compose exporter services.

`GET /metrics` does not call Postgres, Redis, MinIO, DeepSeek, or n8n. It only
renders the in-process registry.

## Metric Contract

Application metrics use the `rag_` prefix:

- `rag_http_requests_total`
- `rag_http_request_duration_seconds`
- `rag_queries_total`
- `rag_retrieval_duration_seconds`
- `rag_vector_search_duration_seconds`
- `rag_keyword_search_duration_seconds`
- `rag_rerank_duration_seconds`
- `rag_retrieved_chunks`
- `rag_ingestion_documents_total`
- `rag_ingestion_duration_seconds`
- `rag_ingestion_chunks_total`
- `rag_embedding_duration_seconds`
- `rag_llm_requests_total`
- `rag_llm_request_duration_seconds`
- `rag_llm_input_tokens_total`
- `rag_llm_output_tokens_total`
- `rag_llm_estimated_cost_usd_total`
- `rag_errors_total`
- `rag_cache_hits_total`
- `rag_cache_misses_total`
- `rag_worker_jobs_total`
- `rag_worker_job_duration_seconds`
- `rag_worker_queue_depth`

Prometheus labels are bounded. Do not add labels for user, tenant, request,
document, version, job, filename, prompt, or raw query identifiers. Request IDs
belong in logs only.

## Structured Logs

JSON logs include request correlation through `request_id` and use safe
diagnostic fields such as `stage`, `dependency`, `status`, `latency_ms`,
`model`, and `error_code`. The formatter redacts credential-like values and
private prompt, query, and document text extras recursively.

Structured study generation uses the provider usage metadata path, so its LLM
requests contribute to request, latency, token, and estimated-cost metrics when
the provider reports usage.

## Local Compose

Start observability alongside the backing services:

```powershell
docker compose --profile worker --profile observability up
```

The observability profile includes:

- `prometheus`
- `grafana`
- `postgres-exporter`
- `redis-exporter`

The worker runs with `WORKER_POOL=threads` by default. Keep a shared-process
worker pool when scraping the in-process worker registry; a prefork pool would
put task metric updates in child process memory that Prometheus cannot scrape
through the parent worker endpoint. In compose, the worker listener remains
fixed at `worker:9108` for Prometheus; set `WORKER_METRICS_HOST_PORT` only when
the host-side port needs to change.

The optional container metrics profile adds cAdvisor:

```powershell
docker compose --profile worker --profile observability --profile container-observability up
```

Prometheus reads `infra/prometheus/prometheus.yml` and
`infra/prometheus/alerts.yml`. The API scrape target assumes the API is running
on the host at `localhost:8000`, which Prometheus reaches as
`host.docker.internal:8000`.

Grafana reads:

- `infra/grafana/provisioning/datasources/prometheus.yml`
- `infra/grafana/provisioning/dashboards/rag.yml`
- `infra/grafana/dashboards/*.json`

Local Grafana runs at `http://localhost:${GRAFANA_PORT:-3000}`. The default
login is `GRAFANA_ADMIN_USER=admin` and
`GRAFANA_ADMIN_PASSWORD=replace-with-local-grafana-password`; change the
password in local `.env` before starting Grafana. Production must override the
admin password through secret-backed environment configuration and must never
commit the real value.

The provisioned dashboards are:

- RAG System Overview
- Retrieval Performance
- LLM / DeepSeek
- Ingestion
- Infrastructure
- n8n

The n8n dashboard uses aggregate workflow and queue metrics only. Keep
`N8N_METRICS=true`, `N8N_METRICS_INCLUDE_DEFAULT_METRICS=true`, and
`N8N_METRICS_INCLUDE_QUEUE_METRICS=true` for the compose dashboard contract.

## Verification

Run:

```powershell
uv run python scripts/validate-prometheus-config.py
uv run python scripts/validate-grafana-dashboards.py
.\scripts\verify-phase-10.ps1
.\scripts\verify-phase-11.ps1
```

The Phase 15 verifier covers Prometheus and Grafana validators, compose config,
lint, typecheck, tests, secret scan, and diff hygiene. Earlier phase verifiers
remain available when a change needs a narrower observability regression.
