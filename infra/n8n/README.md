# n8n Orchestration

Phase 09 adds n8n as the platform's asynchronous workflow console. It is not in the synchronous chat path.

## Runtime

Start n8n with the compose stack:

```powershell
docker compose up -d redis n8n
```

The service persists state in the `n8n_data` Docker volume and exposes the editor on `http://localhost:5678` by default. The default image is pinned with `N8N_IMAGE=docker.n8n.io/n8nio/n8n:2.37.11` and can be overridden locally. Metrics are enabled with `N8N_METRICS=true`, so later Prometheus phases can scrape n8n's `/metrics` endpoint.

## Configuration

Use `.env` for local runtime values:

- `N8N_IMAGE`: container image reference.
- `N8N_HOST`, `N8N_PORT`, `N8N_PROTOCOL`, `N8N_WEBHOOK_URL`: editor and webhook URL settings.
- `N8N_ENCRYPTION_KEY`: stable local encryption key for n8n credentials.
- `N8N_NOTIFICATION_WEBHOOK_URL`: optional outbound alert webhook used only by `failure-notification.json`.
- `RAG_API_BASE_URL`: API base URL visible from the n8n container.
- `RAG_WORKFLOW_OWNER_ID`: development owner header used by local dev-auth flows.
- `N8N_STUDY_TOPIC`: default topic for the daily flashcard workflow.

Never commit `.env`, exported credentials, credential IDs, or provider tokens. Workflow JSON in `workflows/n8n/` is intentionally inactive and credential-free.

## Imports

Import these files in the n8n UI:

- `workflows/n8n/document-ingestion-orchestrator.json`
- `workflows/n8n/scheduled-knowledge-sync.json`
- `workflows/n8n/nightly-rag-evaluation.json`
- `workflows/n8n/daily-study-automation.json`
- `workflows/n8n/failure-notification.json`

After import, create credentials manually in n8n or supply environment variables. Keep workflows inactive until the API, worker, and chosen notification endpoint are running.

Workflow POSTs are retry-safe for the Phase 09 contracts where retries are enabled: report rows deduplicate by workflow execution `run_id` and status, while the nightly evaluation trigger sends `$execution.id` as `idempotency_key`. The daily flashcard-generation POST is not retried because the study endpoint creates chat history and LLM output. The optional outbound notification webhook is also not retried because its receiver is arbitrary and may not deduplicate.

## Validation

Run the source-control validator before committing workflow changes:

```powershell
uv run python scripts/validate-n8n-workflows.py
```

The validator checks workflow names, trigger types, required bounded API endpoints, bounded HTTP retries, inactive default state, no embedded `credentials` blocks, no credential-shaped strings, and no calls to synchronous chat routes.
