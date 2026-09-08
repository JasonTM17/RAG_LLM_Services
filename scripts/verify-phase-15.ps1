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

$gitRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $gitRoot) {
    throw "Not inside a Git repository"
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne "main" -and -not $branch.StartsWith("ci/") -and -not $branch.StartsWith("docs/")) {
    throw "Expected branch main, ci/*, or docs/*, got $branch"
}

@(
    ".github/workflows/ci.yml",
    ".github/workflows/container-build.yml",
    ".github/workflows/security.yml",
    ".dockerignore",
    "apps/api/Dockerfile",
    "apps/worker/Dockerfile",
    "apps/web/Dockerfile",
    "scripts/validate-github-workflows.py",
    "scripts/docs-check.py",
    "docs/architecture/system-overview.md",
    "docs/rag/ingestion-pipeline.md",
    "docs/rag/retrieval-pipeline.md",
    "docs/agent/agent-architecture.md",
    "docs/n8n/workflows.md",
    "docs/observability/metrics.md",
    "docs/deployment/docker.md",
    "docs/security/threat-model.md",
    "CONTRIBUTING.md",
    "$planDir/phase-15-ci-cd-and-documentation.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run python scripts/validate-github-workflows.py
if ($LASTEXITCODE -ne 0) {
    throw "GitHub workflow validation failed"
}

uv run python scripts/docs-check.py
if ($LASTEXITCODE -ne 0) {
    throw "documentation validation failed"
}

uv run python scripts/validate-n8n-workflows.py
if ($LASTEXITCODE -ne 0) {
    throw "n8n workflow validation failed"
}

uv run python scripts/validate-prometheus-config.py
if ($LASTEXITCODE -ne 0) {
    throw "Prometheus validation failed"
}

uv run python scripts/validate-grafana-dashboards.py
if ($LASTEXITCODE -ne 0) {
    throw "Grafana validation failed"
}

uv run python scripts/run-eval.py
if ($LASTEXITCODE -ne 0) {
    throw "fixture-safe evaluation failed"
}

pnpm install --frozen-lockfile
if ($LASTEXITCODE -ne 0) {
    throw "pnpm install failed"
}

pnpm web:lint
if ($LASTEXITCODE -ne 0) {
    throw "web lint failed"
}

pnpm web:typecheck
if ($LASTEXITCODE -ne 0) {
    throw "web type-check failed"
}

pnpm web:test
if ($LASTEXITCODE -ne 0) {
    throw "web tests failed"
}

pnpm web:build
if ($LASTEXITCODE -ne 0) {
    throw "web build failed"
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

uv run python scripts/secret-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "secret scan failed"
}

uv run python scripts/sql-parameterization-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "SQL parameterization scan failed"
}

uv run python scripts/dependency-scan.py
if ($LASTEXITCODE -ne 0) {
    throw "dependency scan failed"
}

docker compose --profile api --profile worker --profile web --profile observability --profile container-observability config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose config failed"
}

docker build --pull -f apps/api/Dockerfile -t rag-llm-services-api:phase15 .
if ($LASTEXITCODE -ne 0) {
    throw "API image build failed"
}

docker build --pull -f apps/worker/Dockerfile -t rag-llm-services-worker:phase15 .
if ($LASTEXITCODE -ne 0) {
    throw "worker image build failed"
}

docker build --pull -f apps/web/Dockerfile -t rag-llm-services-web:phase15 .
if ($LASTEXITCODE -ne 0) {
    throw "web image build failed"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_15_VERIFY_PASS"
