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
Assert-Command pnpm
Assert-Command rg

$gitRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $gitRoot) {
    throw "Not inside a Git repository"
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne "main" -and -not $branch.StartsWith("security/")) {
    throw "Expected branch main or a security/ branch, got $branch"
}

@(
    "apps/api/src/rag_llm_services_api/core/security.py",
    "apps/api/src/rag_llm_services_api/core/rate_limit.py",
    "packages/agents/src/rag_llm_services_agents/prompt_security.py",
    "scripts/secret-scan.py",
    "scripts/dependency-scan.py",
    "scripts/sql-parameterization-scan.py",
    "tests/security/test_cors_config.py",
    "tests/security/test_rate_limit.py",
    "tests/security/test_upload_abuse.py",
    "tests/security/test_prompt_injection.py",
    "tests/security/test_citation_abuse.py",
    "tests/security/test_secret_redaction.py",
    "docs/security/threat-model.md",
    "$planDir/phase-14-security-hardening.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run pytest -q tests/security tests/unit/api/test_config.py tests/unit/api/test_middleware.py tests/unit/documents/test_upload_validation.py tests/unit/agents/test_prompt_injection_guard.py tests/unit/agents/test_citation_validator.py tests/integration/documents/test_document_api.py tests/integration/llm/test_chat_mocked.py
if ($LASTEXITCODE -ne 0) {
    throw "security focused tests failed"
}

uv run python scripts/secret-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "secret and logging scan failed"
}

uv run python scripts/sql-parameterization-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "SQL parameterization scan failed"
}

uv run python scripts/dependency-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "dependency scan failed"
}

uv run ruff check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff check failed"
}

uv run ruff format --check .
if ($LASTEXITCODE -ne 0) {
    throw "ruff format check failed"
}

uv run mypy apps/api/src apps/worker/src packages evals
if ($LASTEXITCODE -ne 0) {
    throw "mypy failed"
}

uv run pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_14_VERIFY_PASS"
