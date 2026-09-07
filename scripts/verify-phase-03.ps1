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
    "docker-compose.yml",
    "apps/api/pyproject.toml",
    "apps/api/alembic.ini",
    "apps/api/src/rag_llm_services_api/main.py",
    "apps/api/src/rag_llm_services_api/domain/documents.py",
    "apps/api/src/rag_llm_services_api/domain/knowledge_bases.py",
    "apps/api/src/rag_llm_services_api/db/models/document.py",
    "apps/api/src/rag_llm_services_api/db/models/knowledge_base.py",
    "apps/api/src/rag_llm_services_api/db/models/chunk.py",
    "apps/api/src/rag_llm_services_api/db/models/ingestion_job.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0002_document_management.py",
    "apps/api/src/rag_llm_services_api/infrastructure/storage/base.py",
    "apps/api/src/rag_llm_services_api/infrastructure/storage/minio.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/documents.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/knowledge_bases.py",
    "apps/api/src/rag_llm_services_api/application/document_service.py",
    "apps/api/src/rag_llm_services_api/api/dependencies/auth.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/knowledge_bases.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/documents.py",
    "apps/api/src/rag_llm_services_api/api/v1/knowledge_bases.py",
    "apps/api/src/rag_llm_services_api/api/v1/documents.py",
    "apps/api/src/rag_llm_services_api/api/v1/ingestion_jobs.py",
    "tests/unit/documents/test_upload_validation.py",
    "tests/integration/documents/test_document_api.py",
    "$planDir/phase-03-document-management-and-storage.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_api.main; import rag_llm_services_api.application.document_service; import rag_llm_services_api.infrastructure.storage.minio; print('IMPORT_OK')"
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

Write-Host "PHASE_03_VERIFY_PASS"
