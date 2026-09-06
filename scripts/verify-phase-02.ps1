$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$planDir = "plans/260906-2101-rag-llm-services-production-platform"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

Assert-Command git
Assert-Command uv

$gitRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $gitRoot) {
    throw "Not inside a Git repository"
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne "main" -and -not $branch.StartsWith("feat/")) {
    throw "Expected branch main or a feat/ branch, got $branch"
}

@(
    "pyproject.toml",
    "uv.lock",
    "apps/api/pyproject.toml",
    "apps/api/alembic.ini",
    "apps/api/src/rag_llm_services_api/main.py",
    "apps/api/src/rag_llm_services_api/core/config.py",
    "apps/api/src/rag_llm_services_api/core/errors.py",
    "apps/api/src/rag_llm_services_api/core/error_handlers.py",
    "apps/api/src/rag_llm_services_api/core/middleware.py",
    "apps/api/src/rag_llm_services_api/db/session.py",
    "apps/api/src/rag_llm_services_api/db/base.py",
    "apps/api/src/rag_llm_services_api/db/migrations/env.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0001_baseline.py",
    "apps/api/src/rag_llm_services_api/api/health.py",
    "apps/api/src/rag_llm_services_api/api/v1/router.py",
    "packages/shared/pyproject.toml",
    "packages/observability/pyproject.toml",
    "$planDir/phase-02-backend-foundation.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_api.main; import rag_llm_services_shared.errors; import rag_llm_services_observability.logging_setup; print('IMPORT_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Import smoke failed"
}

uv run alembic -c apps/api/alembic.ini history
if ($LASTEXITCODE -ne 0) {
    throw "Alembic baseline is not loadable"
}

uv run ruff check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff check failed"
}

uv run ruff format --check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff format check failed"
}

uv run pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed"
}

rg -n --hidden --pcre2 "sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}" . `
    -g "!**/.env" `
    -g "!**/.git/**" `
    -g "!**/node_modules/**" `
    -g "!**/.venv/**"
if ($LASTEXITCODE -eq 0) {
    throw "Credential-shaped material detected outside local .env files"
}
if ($LASTEXITCODE -gt 1) {
    throw "Secret scan command failed"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_02_VERIFY_PASS"
