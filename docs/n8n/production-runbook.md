# n8n Production Orchestration Runbook

This document is the operational guide and production runbook for running, provisioning, and maintaining n8n workflows within `RAG_LLM_Services`.

## 1. Overview & Architectural Boundaries

n8n serves as the platform's **asynchronous workflow orchestrator**. In accordance with [ADR-005](../adr/ADR-005-n8n-orchestration.md):
- n8n is strictly decoupled from the synchronous chat request path.
- Chat streaming and interactive query execution are handled directly by the FastAPI API and LLM gateway.
- n8n handles scheduled batch triggers, asynchronous document ingestion polling, nightly RAG quality evaluations, and alerting.

```
                      +-------------------+
                      |   Cron / Webhook  |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   n8n Container   |
                      |    (:5678)        |
                      +----+---------+----+
                           |         |
               HTTP GET/POST         | Outbound Alert
                           |         |
                           v         v
+-----------------------------+   +-----------------------------+
| FastAPI API (/api/v1)       |   | External Webhook Receiver   |
| - Ingestion status poll     |   | (Slack / Discord / Telegram)|
| - Nightly evaluation runs   |   +-----------------------------+
| - Automation reports audit  |
+-----------------------------+
```

---

## 2. Automated Workflow Provisioning

The project source-controls 5 inactive, credential-free workflow exports under `workflows/n8n/`.

### Automatic Import via CLI
Rather than manually creating workflows in the web UI, use the automated import tooling:

```powershell
# Start n8n and dependencies
docker compose up -d redis n8n

# Automatically import all 5 workflows into n8n
make n8n-import
# Or directly via PowerShell:
.\scripts\n8n-import-workflows.ps1
```

The `docker-compose.yml` mounts `./workflows/n8n` into `/workflows:ro` inside the container. The CLI command executes `n8n import:workflow --separate --input=/workflows`, which initializes the workflows inside n8n's SQLite store.

---

## 3. Workflow Catalog & Contracts

| Workflow File | Trigger | API Contract | Idempotency & Retry |
| --- | --- | --- | --- |
| `document-ingestion-orchestrator.json` | Webhook (`POST /webhook/rag/document-ingestion-orchestrator`) | Polls `GET /api/v1/ingestion-jobs/{id}` and posts `POST /api/v1/automation/reports` | Retries 3x with backoff (5s). Deduplicated by execution run ID. |
| `scheduled-knowledge-sync.json` | Schedule (Hourly/Daily) | `GET /api/v1/knowledge-bases` and records sync report | Retries 3x with backoff (5s). Read-only sync verification. |
| `nightly-rag-evaluation.json` | Schedule (Nightly 02:00) | `POST /api/v1/evaluations` followed by status check | Retries 3x. Sends `$execution.id` as `idempotency_key` so duplicate retries do not requeue active runs. |
| `daily-study-automation.json` | Schedule (Daily 08:00) | `POST /api/v1/study/flashcards` on `N8N_STUDY_TOPIC` | **No retries** (`maxTries: 1`). Flashcard generation invokes LLM and creates study history. |
| `failure-notification.json` | Error Trigger (`n8n-nodes-base.errorTrigger`) | `POST /api/v1/automation/reports` + external notification | **No retries** on external notification to avoid alert spamming. |

---

## 4. Error Handling & Workflow Linking

`failure-notification.json` is configured as the central error handler:
1. **In n8n Editor**: Open each workflow (`Document Ingestion`, `Scheduled Knowledge Sync`, `Nightly RAG Evaluation`, `Daily Study`).
2. Open **Workflow Settings** (gear icon in the top right).
3. Set **Error Workflow** to `RAG - Failure Notification`.
4. When any node fails, n8n automatically executes `RAG - Failure Notification`, logging the failure to `/api/v1/automation/reports` and sending a notification to `N8N_NOTIFICATION_WEBHOOK_URL`.

---

## 5. Production Authentication Strategy

In local development, n8n uses development header authentication:
```http
X-User-Id: 00000000-0000-0000-0000-000000000001
```

### Transitioning to Production
When `APP_ENV=production`, dev-auth fails closed with `401 Unauthorized`. For production deployments:
1. **Service Account Registration**: Create a dedicated automation user via `POST /api/v1/auth/register` (e.g., `automation@service.internal`).
2. **JWT Authentication Node**:
   - In n8n, add a preliminary HTTP node calling `POST /api/v1/auth/login` using the automation user's credentials.
   - Extract the `access_token` from the response.
   - Pass `Authorization: Bearer {{ $json.access_token }}` in downstream API request headers.
3. Alternatively, supply a long-lived JWT token via environment variable `RAG_AUTOMATION_SERVICE_TOKEN` to the n8n container environment.

---

## 6. Outbound Notifications Configuration

To receive alerts when workflows fail, configure `N8N_NOTIFICATION_WEBHOOK_URL` in `.env`:

### Slack
1. Create an Incoming Webhook in your Slack Workspace.
2. Set in `.env`:
   ```env
   N8N_NOTIFICATION_WEBHOOK_URL=https://hooks.slack.com/services/T000/B000/XXXX
   ```

### Discord
1. Create a Webhook in Discord Channel Settings.
2. Append `/slack` to the Discord URL to support Slack-formatted payloads:
   ```env
   N8N_NOTIFICATION_WEBHOOK_URL=https://discord.com/api/webhooks/123/abc/slack
   ```

### Telegram
Use a webhook relay or bridge endpoint pointing to your Telegram Bot API.

---

## 7. Verification & Health Monitoring

### Automated Verification Script
Run the verification script to validate workflow contracts and probe container health:

```powershell
.\scripts\verify-n8n.ps1
```

### Metrics & Grafana Observability
- **Prometheus Scrape Target**: `n8n:5678/metrics` is scraped automatically by the Prometheus service.
- **Grafana Dashboard**: Provisioned at `http://localhost:3000` via [n8n.json](../../infra/grafana/dashboards/n8n.json), monitoring:
  * Total workflow executions.
  * Execution success vs. failure rates.
  * Node execution latency and memory usage.

### Secret Hygiene
Never commit credentials in workflow JSON. Workflow exports in `workflows/n8n/` must pass:
```powershell
uv run python scripts/validate-n8n-workflows.py
```
This validator strictly enforces absence of `credentials` blocks, tokens, and synchronous chat endpoint calls.
