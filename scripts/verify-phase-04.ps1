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
    "packages/rag/pyproject.toml",
    "packages/rag/src/rag_llm_services_rag/__init__.py",
    "packages/rag/src/rag_llm_services_rag/parsers/base.py",
    "packages/rag/src/rag_llm_services_rag/parsers/text.py",
    "packages/rag/src/rag_llm_services_rag/parsers/markdown.py",
    "packages/rag/src/rag_llm_services_rag/parsers/pdf.py",
    "packages/rag/src/rag_llm_services_rag/parsers/docx.py",
    "packages/rag/src/rag_llm_services_rag/parsers/registry.py",
    "packages/rag/src/rag_llm_services_rag/normalization.py",
    "packages/rag/src/rag_llm_services_rag/chunking.py",
    "packages/embeddings/pyproject.toml",
    "packages/embeddings/src/rag_llm_services_embeddings/__init__.py",
    "packages/embeddings/src/rag_llm_services_embeddings/base.py",
    "packages/embeddings/src/rag_llm_services_embeddings/fake.py",
    "packages/embeddings/src/rag_llm_services_embeddings/bge_m3.py",
    "apps/api/src/rag_llm_services_api/db/models/document_chunk.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0003_document_chunks_pgvector.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/chunks.py",
    "apps/api/src/rag_llm_services_api/infrastructure/embeddings.py",
    "apps/api/src/rag_llm_services_api/application/ingestion_pipeline.py",
    "tests/unit/rag/test_parsers.py",
    "tests/unit/rag/test_chunking.py",
    "tests/unit/embeddings/test_embedding_provider.py",
    "tests/integration/rag/test_ingestion_pipeline.py",
    "$planDir/phase-04-rag-ingestion-and-embeddings.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_rag; import rag_llm_services_embeddings; import rag_llm_services_api.application.ingestion_pipeline; print('IMPORT_OK')"
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

Write-Host "PHASE_04_VERIFY_PASS"
