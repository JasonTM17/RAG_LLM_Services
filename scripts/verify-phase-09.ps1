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
    "docker-compose.yml",
    "infra/n8n/README.md",
    "docs/n8n/workflows.md",
    "workflows/n8n/document-ingestion-orchestrator.json",
    "workflows/n8n/scheduled-knowledge-sync.json",
    "workflows/n8n/nightly-rag-evaluation.json",
    "workflows/n8n/daily-study-automation.json",
    "workflows/n8n/failure-notification.json",
    "scripts/validate-n8n-workflows.py",
    "apps/api/src/rag_llm_services_api/api/v1/automation.py",
    "apps/api/src/rag_llm_services_api/api/v1/evaluations.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/automation.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0007_n8n_automation_contracts.py",
    "apps/api/src/rag_llm_services_api/db/models/automation.py",
    "apps/api/src/rag_llm_services_api/domain/automation.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/automation.py",
    "tests/unit/workflows/test_n8n_exports.py",
    "tests/integration/workflows/test_automation_api.py",
    "$planDir/phase-09-n8n-automation-workflows.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_api.api.v1.automation; import rag_llm_services_api.api.v1.evaluations; print('IMPORT_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Import smoke failed"
}

uv run alembic -c apps/api/alembic.ini history
if ($LASTEXITCODE -ne 0) {
    throw "Alembic history is not loadable"
}

uv run python scripts/validate-n8n-workflows.py
if ($LASTEXITCODE -ne 0) {
    throw "n8n workflow validation failed"
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed"
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

rg -n "/api/v1/chat|/chat/stream|/chat['""]|/chat\s" workflows/n8n
if ($LASTEXITCODE -eq 0) {
    throw "n8n workflows must not call synchronous chat routes"
}
if ($LASTEXITCODE -gt 1) {
    throw "n8n chat-route scan failed"
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

Write-Host "PHASE_09_VERIFY_PASS"
