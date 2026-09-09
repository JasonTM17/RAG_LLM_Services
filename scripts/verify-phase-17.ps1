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
Assert-Command docker
Assert-Command rg

@(
    "apps/api/src/rag_llm_services_api/api/v1/auth.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/auth.py",
    "apps/api/src/rag_llm_services_api/core/passwords.py",
    "apps/api/src/rag_llm_services_api/core/tokens.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0008_user_accounts.py",
    "apps/api/src/rag_llm_services_api/db/models/user.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/users.py",
    "tests/unit/api/test_passwords.py",
    "tests/unit/api/test_tokens.py",
    "tests/integration/api/test_auth_api.py",
    "$planDir/phase-17-production-auth-and-restore-rehearsal.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

Write-Host "Running focused auth tests..." -ForegroundColor Green
uv run pytest -q tests/unit/api/test_passwords.py tests/unit/api/test_tokens.py tests/integration/api/test_auth_api.py
if ($LASTEXITCODE -ne 0) {
    throw "Focused auth tests failed"
}

Write-Host "Running ruff and mypy..." -ForegroundColor Green
uv run ruff check .
if ($LASTEXITCODE -ne 0) {
    throw "Ruff lint failed"
}

uv run ruff format --check .
if ($LASTEXITCODE -ne 0) {
    throw "Ruff format check failed"
}

uv run mypy apps/api/src apps/worker/src packages evals
if ($LASTEXITCODE -ne 0) {
    throw "Mypy typecheck failed"
}

Write-Host "Running full test suite..." -ForegroundColor Green
uv run pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Full pytest suite failed"
}

Write-Host "Running security secret scan..." -ForegroundColor Green
uv run python scripts/secret-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "Secret scan failed"
}

Write-Host "Running documentation check..." -ForegroundColor Green
uv run python scripts/docs-check.py
if ($LASTEXITCODE -ne 0) {
    throw "Documentation validation failed"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_17_VERIFY_PASS" -ForegroundColor Green
