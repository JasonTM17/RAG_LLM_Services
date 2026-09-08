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
Assert-Command ak

@(
    "scripts/acceptance-demo.py",
    "scripts/backup-dry-run.py",
    "scripts/restore-dry-run.py",
    "scripts/compose-smoke.ps1",
    "scripts/verify-phase-16.ps1",
    "$planDir/phase-16-production-review-and-release-readiness.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

.\scripts\verify-phase-15.ps1
if ($LASTEXITCODE -ne 0) {
    throw "Phase 15 regression gate failed"
}

uv run python scripts/acceptance-demo.py
if ($LASTEXITCODE -ne 0) {
    throw "acceptance demo failed"
}

uv run python scripts/backup-dry-run.py
if ($LASTEXITCODE -ne 0) {
    throw "backup dry-run failed"
}

uv run python scripts/restore-dry-run.py
if ($LASTEXITCODE -ne 0) {
    throw "restore dry-run failed"
}

.\scripts\compose-smoke.ps1
if ($LASTEXITCODE -ne 0) {
    throw "compose smoke failed"
}

uv run python scripts/docs-check.py
if ($LASTEXITCODE -ne 0) {
    throw "documentation validation failed"
}

ak plan validate $planDir
if ($LASTEXITCODE -ne 0) {
    throw "plan validation failed"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_16_VERIFY_PASS"
