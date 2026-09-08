# n8n Workflow Contract

The repository source-controls five n8n exports under `workflows/n8n/`. They are orchestration workflows only: chat endpoints remain served directly by the API and LLM gateway.

## Workflow Exports

| File | Trigger | API Contract |
| --- | --- | --- |
| `document-ingestion-orchestrator.json` | Webhook | Polls `GET /api/v1/ingestion-jobs/{job_id}` and records `POST /api/v1/automation/reports`. |
| `scheduled-knowledge-sync.json` | Schedule | Calls `GET /api/v1/knowledge-bases` and records an inventory report. |
| `nightly-rag-evaluation.json` | Schedule | Creates `POST /api/v1/evaluations` with `$execution.id` as `idempotency_key`, fetches `GET /api/v1/evaluations/{run_id}`, and records the current evaluation status/result. |
| `daily-study-automation.json` | Schedule | Calls `POST /api/v1/study/flashcards` and records the generated study run. |
| `failure-notification.json` | Error trigger | Records workflow failure details and optionally posts to `N8N_NOTIFICATION_WEBHOOK_URL`. |

## API Boundaries

- n8n uses `X-User-Id: ${RAG_WORKFLOW_OWNER_ID}` only for local dev-auth. Production rejects dev auth; a real production auth boundary remains a release gate.
- n8n reports use `POST /api/v1/automation/reports`; reports reject credential-shaped values.
- Retry safety is explicit: report rows deduplicate by owner, workflow, execution `run_id`, and status; evaluation triggers deduplicate by owner and `idempotency_key`.
- `daily-study-automation.json` does not retry `POST /api/v1/study/flashcards` because Phase 07 study generation creates chat history and LLM output. Workflow failure notification handles that error path.
- `failure-notification.json` does not retry the optional external notification webhook because the receiver may not support deduplication.
- Evaluation APIs create idempotent queued runs; the worker executes the fixture-safe Phase 12 runner and persists aggregate metrics/thresholds/report paths in `evaluation_runs`. n8n records the current status as `RUNNING`, `SUCCEEDED`, or `FAILED`; callers that need the final result should keep polling `GET /api/v1/evaluations/{run_id}` until `SUCCEEDED` or `FAILED`.
- Evaluation thresholds are controlled by `EVAL_*_THRESHOLD` variables; misses become `FAILED` evaluation runs with result status `FAIL`, not warning-only reports.
- No workflow may call `POST /api/v1/chat` or `POST /api/v1/chat/stream`.

## Secrets

Workflow exports must not contain n8n `credentials` blocks, bearer tokens, provider keys, webhook secrets, or private document text. Credentials are created manually in n8n or provided through environment variables at runtime.

## Verification

```powershell
uv run python scripts/validate-n8n-workflows.py
uv run python scripts/run-eval.py
uv run pytest -q tests/unit/workflows/test_n8n_exports.py tests/integration/workflows/test_automation_api.py
docker compose config --quiet
```

The Phase 09 verifier wraps these checks with lint, typecheck, Alembic history, secret scan, and `git diff --check`.
