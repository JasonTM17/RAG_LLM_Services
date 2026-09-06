SHELL := powershell
.SHELLFLAGS := -NoProfile -ExecutionPolicy Bypass -Command

PLAN_DIR := plans/260906-2101-rag-llm-services-production-platform

.PHONY: help plan-status verify-phase-01 check-ignore secret-scan acceptance-demo backup-dry-run restore-dry-run

help:
	@Write-Host "RAG_LLM_Services command contract"
	@Write-Host "  make plan-status       Show AgentKit plan status"
	@Write-Host "  make verify-phase-01   Run repository foundation checks"
	@Write-Host "  make check-ignore      Verify .env stays out of Git"
	@Write-Host "  make secret-scan       Scan tracked workspace excluding local env files"

plan-status:
	@ak plan status "$(PLAN_DIR)" --no-interactive

verify-phase-01:
	@.\scripts\verify-phase-01.ps1

check-ignore:
	@git check-ignore -v .env

secret-scan:
	@rg -n --hidden --pcre2 "sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}" . -g "!**/.env" -g "!**/.git/**" -g "!**/node_modules/**" -g "!**/.venv/**"

acceptance-demo:
	@Write-Error "acceptance-demo is introduced after the API, worker, RAG, and observability phases are implemented."; exit 1

backup-dry-run:
	@Write-Error "backup-dry-run is introduced before production release review."; exit 1

restore-dry-run:
	@Write-Error "restore-dry-run is introduced before production release review."; exit 1
