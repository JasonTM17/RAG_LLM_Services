$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$planDir = "plans/260906-2101-rag-llm-services-production-platform"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Resolve-MakeCommand {
    $make = Get-Command make -ErrorAction SilentlyContinue
    if ($make) {
        return $make.Source
    }
    $candidates = @(
        "C:\msys64\usr\bin\make.exe",
        "C:\Program Files\Git\mingw64\bin\make.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

Assert-Command git
Assert-Command uv
Assert-Command rg
Assert-Command docker

$gitRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $gitRoot) {
    throw "Not inside a Git repository"
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne "main" -and -not $branch.StartsWith("feat/")) {
    throw "Expected branch main or a feat/ branch, got $branch"
}

@(
    "evals/datasets/baseline-learning-rag.jsonl",
    "evals/evaluators/retrieval_metrics.py",
    "evals/evaluators/citation_metrics.py",
    "evals/evaluators/answer_metrics.py",
    "evals/runner.py",
    "evals/reports/.gitkeep",
    "apps/api/src/rag_llm_services_api/application/evaluation_service.py",
    "apps/api/src/rag_llm_services_api/api/v1/evaluations.py",
    "apps/api/src/rag_llm_services_api/api/v1/schemas/automation.py",
    "apps/api/src/rag_llm_services_api/infrastructure/queue/base.py",
    "apps/api/src/rag_llm_services_api/infrastructure/queue/redis_queue.py",
    "apps/api/src/rag_llm_services_api/infrastructure/repositories/automation.py",
    "apps/worker/src/rag_llm_services_worker/tasks.py",
    "scripts/run-eval.py",
    "scripts/validate-n8n-workflows.py",
    "workflows/n8n/nightly-rag-evaluation.json",
    "tests/unit/evals/test_retrieval_metrics.py",
    "tests/unit/evals/test_citation_metrics.py",
    "tests/unit/evals/test_answer_metrics.py",
    "tests/unit/api/test_queue.py",
    "tests/unit/workflows/test_n8n_exports.py",
    "tests/integration/evals/test_evaluation_api.py",
    "docs/rag/retrieval-pipeline.md",
    "docs/n8n/workflows.md",
    "docker-compose.yml",
    "$planDir/phase-12-rag-evaluation-framework.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import evals.runner; import rag_llm_services_api.application.evaluation_service; print('IMPORT_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Import smoke failed"
}

$makeCommand = Resolve-MakeCommand
if ($makeCommand) {
    & $makeCommand eval
    if ($LASTEXITCODE -ne 0) {
        throw "make eval failed"
    }
} else {
    Write-Host "MAKE_EVAL_NOT_RUN: make command not found; running underlying eval command"
    uv run python scripts/run-eval.py
    if ($LASTEXITCODE -ne 0) {
        throw "Evaluation runner failed"
    }
}

uv run python scripts/validate-n8n-workflows.py
if ($LASTEXITCODE -ne 0) {
    throw "n8n workflow validation failed"
}

docker compose --profile worker config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose worker config failed"
}

uv run pytest -q tests/unit/api/test_config.py tests/unit/api/test_queue.py tests/unit/workflows/test_n8n_exports.py tests/unit/evals tests/integration/evals/test_evaluation_api.py tests/integration/workflows/test_automation_api.py
if ($LASTEXITCODE -ne 0) {
    throw "Focused evaluation/API tests failed"
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

if (Test-Path -LiteralPath "evals/reports/local") {
    rg -n --no-ignore --hidden --pcre2 "sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}" evals/reports/local `
        -g "!**/.git/**"
    if ($LASTEXITCODE -eq 0) {
        throw "Credential-shaped material detected in generated evaluation reports"
    }
    if ($LASTEXITCODE -gt 1) {
        throw "Evaluation report secret scan command failed"
    }
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

Write-Host "PHASE_12_VERIFY_PASS"
