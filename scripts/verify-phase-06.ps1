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
    "packages/llm/pyproject.toml",
    "packages/llm/src/rag_llm_services_llm/__init__.py",
    "packages/llm/src/rag_llm_services_llm/base.py",
    "packages/llm/src/rag_llm_services_llm/deepseek.py",
    "packages/llm/src/rag_llm_services_llm/errors.py",
    "packages/llm/src/rag_llm_services_llm/usage.py",
    "packages/llm/src/rag_llm_services_llm/costs.py",
    "apps/api/src/rag_llm_services_api/application/chat_service.py",
    "apps/api/src/rag_llm_services_api/api/v1/chat.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/chat.py",
    "apps/api/src/rag_llm_services_api/domain/chat.py",
    "apps/api/src/rag_llm_services_api/db/models/conversation.py",
    "apps/api/src/rag_llm_services_api/db/models/message.py",
    "apps/api/src/rag_llm_services_api/db/models/llm_usage.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0005_chat_and_llm_usage.py",
    "apps/api/src/rag_llm_services_api/infrastructure/llm.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/chat.py",
    "tests/unit/llm/test_deepseek_config.py",
    "tests/unit/llm/test_provider_errors.py",
    "tests/unit/llm/test_cost_calculator.py",
    "tests/unit/llm/test_responses_streaming.py",
    "tests/integration/llm/test_chat_mocked.py",
    "tests/integration/llm/test_deepseek_live_optional.py",
    "$planDir/phase-06-deepseek-llm-provider.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_llm; import rag_llm_services_api.application.chat_service; print('IMPORT_OK')"
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

uv run mypy apps/api/src packages
if ($LASTEXITCODE -ne 0) {
    throw "mypy failed"
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

Write-Host "PHASE_06_VERIFY_PASS"
