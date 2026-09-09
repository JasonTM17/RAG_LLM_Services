SHELL := powershell
.SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command

PLAN_DIR := plans/260906-2101-rag-llm-services-production-platform

.PHONY: help plan-status verify-phase-01 verify-phase-02 verify-phase-03 verify-phase-04 verify-phase-05 verify-phase-06 verify-phase-07 verify-phase-08 verify-phase-09 verify-phase-10 verify-phase-11 verify-phase-12 verify-phase-13 verify-phase-14 verify-phase-15 verify-phase-16 verify-phase-17 eval validate-workflows docs-check validate-n8n n8n-import validate-prometheus validate-grafana check-ignore secret-scan dependency-scan sql-scan container-build dockerhub-build dockerhub-push web-dev web-build web-lint web-typecheck web-test web-e2e web-verify api-test api-lint api-typecheck api-migrate api-run worker-run acceptance-demo backup-dry-run restore-dry-run restore-rehearsal compose-smoke

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
	@Write-Host "  make verify-phase-12   Run RAG evaluation framework checks"
	@Write-Host "  make verify-phase-13   Run frontend app checks"
	@Write-Host "  make verify-phase-14   Run security hardening checks"
	@Write-Host "  make verify-phase-15   Run CI/CD and documentation checks"
	@Write-Host "  make verify-phase-16   Run release readiness checks"
	@Write-Host "  make verify-phase-17   Run production auth checks"
	@Write-Host "  make eval              Run the fixture-safe RAG evaluation"
	@Write-Host "  make validate-workflows Validate GitHub Actions workflow contracts"
	@Write-Host "  make docs-check        Validate documentation paths, links, and ADR shape"
	@Write-Host "  make validate-n8n      Validate source-controlled n8n workflow exports"
	@Write-Host "  make n8n-import        Import workflows into running n8n container"
	@Write-Host "  make validate-prometheus Validate Prometheus scrape and alert contracts"
	@Write-Host "  make validate-grafana  Validate Grafana provisioning and dashboards"
	@Write-Host "  make check-ignore      Verify .env stays out of Git"
	@Write-Host "  make secret-scan       Scan tracked workspace excluding local env files"
	@Write-Host "  make dependency-scan   Run Python and Node vulnerability scans"
	@Write-Host "  make sql-scan          Scan for obvious unsafe SQL execution patterns"
	@Write-Host "  make container-build   Build API, worker, and web images locally"
	@Write-Host "  make dockerhub-build   Build and tag Docker Hub images locally"
	@Write-Host "  make dockerhub-push    Build, tag, and push images to Docker Hub"
	@Write-Host "  make web-dev           Start the Next.js web app locally"
	@Write-Host "  make web-build         Build the Next.js web app"
	@Write-Host "  make web-verify        Run web lint, type-check, and component tests"
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

verify-phase-12:
	@.\scripts\verify-phase-12.ps1

verify-phase-13:
	@.\scripts\verify-phase-13.ps1

verify-phase-14:
	@.\scripts\verify-phase-14.ps1

verify-phase-15:
	@.\scripts\verify-phase-15.ps1

verify-phase-16:
	@.\scripts\verify-phase-16.ps1

verify-phase-17:
	@.\scripts\verify-phase-17.ps1

eval:
	@uv run python scripts/run-eval.py

validate-workflows:
	@uv run python scripts/validate-github-workflows.py

docs-check:
	@uv run python scripts/docs-check.py

validate-n8n:
	@uv run python scripts/validate-n8n-workflows.py

n8n-import:
	@.\scripts\n8n-import-workflows.ps1

validate-prometheus:
	@uv run python scripts/validate-prometheus-config.py

validate-grafana:
	@uv run python scripts/validate-grafana-dashboards.py


check-ignore:
	@git check-ignore -v .env

secret-scan:
	@uv run python scripts/secret-scan.py

dependency-scan:
	@uv run python scripts/dependency-scan.py

sql-scan:
	@uv run python scripts/sql-parameterization-scan.py

container-build:
	@docker build --pull -f apps/api/Dockerfile -t rag-llm-services-api:local .
	@docker build --pull -f apps/worker/Dockerfile -t rag-llm-services-worker:local .
	@docker build --pull -f apps/web/Dockerfile -t rag-llm-services-web:local .

dockerhub-build:
	@.\scripts\publish-docker-hub.ps1

dockerhub-push:
	@.\scripts\publish-docker-hub.ps1 -Push

web-dev:
	@pnpm web:dev

web-build:
	@pnpm web:build

web-lint:
	@pnpm web:lint

web-typecheck:
	@pnpm web:typecheck

web-test:
	@pnpm web:test

web-e2e:
	@pnpm web:e2e

web-verify:
	@pnpm web:verify

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
	@uv run python scripts/acceptance-demo.py

backup-dry-run:
	@uv run python scripts/backup-dry-run.py

restore-dry-run:
	@uv run python scripts/restore-dry-run.py

restore-rehearsal:
	@.\scripts\restore-rehearsal.ps1

compose-smoke:
	@.\scripts\compose-smoke.ps1
