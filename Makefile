SHELL := powershell
.SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command

PLAN_DIR := plans/260906-2101-rag-llm-services-production-platform

.PHONY: help plan-status verify-phase-01 verify-phase-02 verify-phase-03 verify-phase-04 verify-phase-05 verify-phase-06 verify-phase-07 verify-phase-08 verify-phase-09 verify-phase-10 verify-phase-11 validate-n8n validate-prometheus validate-grafana check-ignore secret-scan api-test api-lint api-typecheck api-migrate api-run worker-run acceptance-demo backup-dry-run restore-dry-run

help:
	@Write-Host "RAG_LLM_Services command contract"
	@Write-Host "  make plan-status       Show AgentKit plan status"
	@Write-Host "  make verify-phase-01   Run repository foundation checks"
	@Write-Host "  make verify-phase-02   Run backend foundation checks"
	@Write-Host "  make verify-phase-03   Run document management checks"
	@Write-Host "  make verify-phase-04   Run RAG ingestion and embeddings checks"
	@Write-Host "  make verify-phase-05   Run hybrid retrieval and reranking checks"
	@Write-Host "  make verify-phase-06   Run DeepSeek provider and mocked chat checks"
	@Write-Host "  make verify-phase-07   Run agent layer and study workflow checks"
	@Write-Host "  make verify-phase-08   Run async worker and Redis queue checks"
	@Write-Host "  make verify-phase-09   Run n8n workflow and compose checks"
	@Write-Host "  make verify-phase-10   Run Prometheus metrics and observability checks"
	@Write-Host "  make verify-phase-11   Run Grafana dashboard and provisioning checks"
	@Write-Host "  make validate-n8n      Validate source-controlled n8n workflow exports"
	@Write-Host "  make validate-prometheus Validate Prometheus scrape and alert contracts"
	@Write-Host "  make validate-grafana  Validate Grafana provisioning and dashboards"
	@Write-Host "  make check-ignore      Verify .env stays out of Git"
	@Write-Host "  make secret-scan       Scan tracked workspace excluding local env files"
	@Write-Host "  make api-test          Run the full pytest suite through uv"
	@Write-Host "  make api-lint          Run ruff check and format check"
	@Write-Host "  make api-typecheck     Run mypy"
	@Write-Host "  make api-migrate       Apply Alembic migrations to the configured database"
	@Write-Host "  make api-run           Start the API locally with uvicorn (reload)"
	@Write-Host "  make worker-run        Start the Celery ingestion worker locally"

plan-status:
	@ak plan status "$(PLAN_DIR)" --no-interactive

verify-phase-01:
	@.\scripts\verify-phase-01.ps1

verify-phase-02:
	@.\scripts\verify-phase-02.ps1

verify-phase-03:
	@.\scripts\verify-phase-03.ps1

verify-phase-04:
	@.\scripts\verify-phase-04.ps1

verify-phase-05:
	@.\scripts\verify-phase-05.ps1

verify-phase-06:
	@.\scripts\verify-phase-06.ps1

verify-phase-07:
	@.\scripts\verify-phase-07.ps1

verify-phase-08:
	@.\scripts\verify-phase-08.ps1

verify-phase-09:
	@.\scripts\verify-phase-09.ps1

verify-phase-10:
	@.\scripts\verify-phase-10.ps1

verify-phase-11:
	@.\scripts\verify-phase-11.ps1

validate-n8n:
	@uv run python scripts/validate-n8n-workflows.py

validate-prometheus:
	@uv run python scripts/validate-prometheus-config.py

validate-grafana:
	@uv run python scripts/validate-grafana-dashboards.py


check-ignore:
	@git check-ignore -v .env

secret-scan:
	@rg -n --hidden --pcre2 "sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}" . -g "!**/.env" -g "!**/.git/**" -g "!**/node_modules/**" -g "!**/.venv/**"

api-test:
	@uv run pytest -q

api-lint:
	@uv run ruff check .; if ($$LASTEXITCODE -ne 0) { exit 1 }
	@uv run ruff format --check .

api-typecheck:
	@uv run mypy apps/api/src apps/worker/src packages

api-migrate:
	@uv run alembic -c apps/api/alembic.ini upgrade head

api-run:
	@uv run uvicorn rag_llm_services_api.main:app --reload --env-file .env --port 8000

worker-run:
	@$$queue = if ($$env:INGESTION_QUEUE_NAME) { $$env:INGESTION_QUEUE_NAME } else { "ingestion" }; uv run celery -A rag_llm_services_worker.main:celery_app worker --loglevel=INFO --queues $$queue

acceptance-demo:
	@Write-Error "acceptance-demo is introduced after the API, worker, RAG, and observability phases are implemented."; exit 1

backup-dry-run:
	@Write-Error "backup-dry-run is introduced before production release review."; exit 1

restore-dry-run:
	@Write-Error "restore-dry-run is introduced before production release review."; exit 1
