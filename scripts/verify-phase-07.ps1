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
    "packages/agents/pyproject.toml",
    "packages/agents/src/rag_llm_services_agents/__init__.py",
    "packages/agents/src/rag_llm_services_agents/citations.py",
    "packages/agents/src/rag_llm_services_agents/context_window.py",
    "packages/agents/src/rag_llm_services_agents/prompts.py",
    "packages/agents/src/rag_llm_services_agents/rag_agent.py",
    "packages/agents/src/rag_llm_services_agents/router_agent.py",
    "packages/agents/src/rag_llm_services_agents/runtime.py",
    "packages/agents/src/rag_llm_services_agents/study_agent.py",
    "packages/agents/src/rag_llm_services_agents/tools.py",
    "apps/api/src/rag_llm_services_api/application/agent_service.py",
    "apps/api/src/rag_llm_services_api/api/v1/study.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/study.py",
    "tests/unit/agents/test_router_intents.py",
    "tests/unit/agents/test_tool_bounds.py",
    "tests/unit/agents/test_citation_validator.py",
    "tests/unit/agents/test_prompt_injection_guard.py",
    "tests/unit/agents/test_sdk_runtime.py",
    "tests/integration/agents/test_study_mocked.py",
    "$planDir/phase-07-agent-layer-and-study-workflows.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import agents; import rag_llm_services_agents; import rag_llm_services_api.application.agent_service; print('IMPORT_OK')"
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

rg -n "from sqlalchemy|session\.execute|AsyncSession|DocumentModel|KnowledgeBaseModel" packages/agents/src
if ($LASTEXITCODE -eq 0) {
    throw "Agent package must not query database models or sessions directly"
}
if ($LASTEXITCODE -gt 1) {
    throw "Agent DB-boundary scan failed"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_07_VERIFY_PASS"
