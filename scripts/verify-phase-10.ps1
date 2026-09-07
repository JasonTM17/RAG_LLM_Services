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
    "packages/observability/src/rag_llm_services_observability/metrics.py",
    "packages/observability/src/rag_llm_services_observability/logging_setup.py",
    "apps/api/src/rag_llm_services_api/api/metrics.py",
    "apps/api/src/rag_llm_services_api/core/middleware.py",
    "apps/api/src/rag_llm_services_api/application/retrieval_service.py",
    "apps/api/src/rag_llm_services_api/application/ingestion_pipeline.py",
    "apps/api/src/rag_llm_services_api/application/chat_service.py",
    "apps/worker/src/rag_llm_services_worker/main.py",
    "apps/worker/src/rag_llm_services_worker/metrics.py",
    "apps/worker/src/rag_llm_services_worker/tasks.py",
    "infra/prometheus/prometheus.yml",
    "infra/prometheus/alerts.yml",
    "scripts/validate-prometheus-config.py",
    "tests/unit/observability/test_metric_labels.py",
    "tests/integration/observability/test_metrics_endpoint.py",
    "docs/observability/metrics.md",
    "$planDir/phase-10-prometheus-metrics-and-observability.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python -c "import rag_llm_services_api.api.metrics; import rag_llm_services_api.main; import rag_llm_services_observability.metrics; import rag_llm_services_worker.main; print('IMPORT_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Import smoke failed"
}

uv run python scripts/validate-prometheus-config.py
if ($LASTEXITCODE -ne 0) {
    throw "Prometheus config validation failed"
}

docker compose --profile observability --profile worker --profile container-observability config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose observability config failed"
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

uv run python -c "from rag_llm_services_observability.metrics import validate_metric_label_policy; errors = validate_metric_label_policy(); assert not errors, errors; print('METRIC_LABEL_POLICY_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Metric label policy validation failed"
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

Write-Host "PHASE_10_VERIFY_PASS"
