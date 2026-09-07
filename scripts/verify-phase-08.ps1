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
Assert-Command rg

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
    "apps/worker/pyproject.toml",
    "apps/worker/src/rag_llm_services_worker/__init__.py",
    "apps/worker/src/rag_llm_services_worker/main.py",
    "apps/worker/src/rag_llm_services_worker/tasks.py",
    "apps/worker/src/rag_llm_services_worker/retry.py",
    "apps/worker/src/rag_llm_services_worker/metrics.py",
    "apps/api/src/rag_llm_services_api/infrastructure/queue/base.py",
    "apps/api/src/rag_llm_services_api/infrastructure/queue/redis_queue.py",
    "apps/api/src/rag_llm_services_api/infrastructure/queue/__init__.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0006_async_worker_job_metadata.py",
    "packages/shared/src/rag_llm_services_shared/cache_keys.py",
    "tests/unit/worker/test_retry_policy.py",
    "tests/unit/shared/test_cache_keys.py",
    "tests/integration/worker/test_ingestion_task.py",
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "docs/adr/ADR-006-redis-worker-architecture.md",
    "$planDir/phase-08-async-infrastructure-and-redis.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import celery; import rag_llm_services_worker; import rag_llm_services_api.infrastructure.queue; print('IMPORT_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Import smoke failed"
}

uv run alembic -c apps/api/alembic.ini history
if ($LASTEXITCODE -ne 0) {
    throw "Alembic history is not loadable"
}

uv run ruff check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff check failed"
}

uv run ruff format --check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff format check failed"
}

uv run mypy apps/api/src apps/worker/src packages
if ($LASTEXITCODE -ne 0) {
    throw "mypy failed"
}

uv run pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed"
}

$compose = Get-Content -Raw docker-compose.yml
foreach ($required in @("redis:", "healthcheck:", "worker:", "CELERY_BROKER_URL", "INGESTION_QUEUE_NAME")) {
    if (-not $compose.Contains($required)) {
        throw "docker-compose.yml missing async infrastructure marker: $required"
    }
}

rg -n "fastapi|APIRouter|rag_llm_services_api\.api" apps/worker/src
if ($LASTEXITCODE -eq 0) {
    throw "Worker package must not import FastAPI route layer"
}
if ($LASTEXITCODE -gt 1) {
    throw "Worker route-boundary scan failed"
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

Write-Host "PHASE_08_VERIFY_PASS"
