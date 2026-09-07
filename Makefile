SHELL := powershell
.SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command

PLAN_DIR := plans/260906-2101-rag-llm-services-production-platform

.PHONY: help plan-status verify-phase-01 verify-phase-02 verify-phase-03 verify-phase-04 check-ignore secret-scan api-test api-lint api-typecheck api-migrate api-run acceptance-demo backup-dry-run restore-dry-run

help:
	@Write-Host "RAG_LLM_Services command contract"
	@Write-Host "  make plan-status       Show AgentKit plan status"
	@Write-Host "  make verify-phase-01   Run repository foundation checks"
	@Write-Host "  make verify-phase-02   Run backend foundation checks"
	@Write-Host "  make verify-phase-03   Run document management checks"
	@Write-Host "  make verify-phase-04   Run RAG ingestion and embeddings checks"
	@Write-Host "  make check-ignore      Verify .env stays out of Git"
	@Write-Host "  make secret-scan       Scan tracked workspace excluding local env files"
	@Write-Host "  make api-test          Run the full pytest suite through uv"
	@Write-Host "  make api-lint          Run ruff check and format check"
	@Write-Host "  make api-typecheck     Run mypy"
	@Write-Host "  make api-migrate       Apply Alembic migrations to the configured database"
	@Write-Host "  make api-run           Start the API locally with uvicorn (reload)"

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
	@uv run mypy apps/api/src packages

api-migrate:
	@uv run alembic -c apps/api/alembic.ini upgrade head

api-run:
	@uv run uvicorn rag_llm_services_api.main:app --reload --env-file .env --port 8000

acceptance-demo:
	@Write-Error "acceptance-demo is introduced after the API, worker, RAG, and observability phases are implemented."; exit 1

backup-dry-run:
	@Write-Error "backup-dry-run is introduced before production release review."; exit 1

restore-dry-run:
	@Write-Error "restore-dry-run is introduced before production release review."; exit 1
