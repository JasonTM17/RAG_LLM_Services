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
    "packages/rag/src/rag_llm_services_rag/retrieval/__init__.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/types.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/query.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/vector.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/keyword.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/fusion.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/reranker.py",
    "packages/rag/src/rag_llm_services_rag/retrieval/context.py",
    "apps/api/src/rag_llm_services_api/application/retrieval_service.py",
    "apps/api/src/rag_llm_services_api/api/v1/retrieval.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/retrieval.py",
    "apps/api/src/rag_llm_services_api/db/models/rag_query.py",
    "apps/api/src/rag_llm_services_api/db/migrations/versions/0004_hybrid_retrieval_and_rag_queries.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/rag_queries.py",
    "apps/api/src/rag_llm_services_api/infrastructure/reranker.py",
    "tests/unit/rag/test_reciprocal_rank_fusion.py",
    "tests/unit/rag/test_context_builder.py",
    "tests/unit/rag/test_retrieval_components.py",
    "tests/integration/rag/test_hybrid_retrieval.py",
    "$planDir/phase-05-hybrid-retrieval-and-reranking.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_rag.retrieval; import rag_llm_services_api.application.retrieval_service; print('IMPORT_OK')"
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

Write-Host "PHASE_05_VERIFY_PASS"
