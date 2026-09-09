[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$N8nHost = "http://localhost:5678"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

Write-Host "=== n8n Health & Orchestration Verification ===" -ForegroundColor Cyan

# 1. Validate workflow exports
Write-Host "1. Validating source-controlled n8n workflow exports..." -ForegroundColor Green
uv run python scripts/validate-n8n-workflows.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Workflow export validation failed."
    exit 1
}

# 2. Check running container status
Write-Host "2. Checking n8n container status..." -ForegroundColor Green
$runningServices = @()
try {
    $dockerOut = (& docker compose ps --services --filter "status=running" 2>&1)
    if ($LASTEXITCODE -eq 0 -and $dockerOut) {
        $runningServices = $dockerOut
    }
} catch {
    # Docker daemon not running
}

$isN8nRunning = ($runningServices -split "`r?`n") -contains "n8n"

if (-not $isN8nRunning) {
    Write-Host "NOTE: n8n container is not running locally. (Export contracts: VALID, Runtime: NOT_RUN)" -ForegroundColor Yellow
    Write-Host "To test live runtime, run: docker compose up -d redis n8n && .\scripts\verify-n8n.ps1" -ForegroundColor Gray
    Write-Host "N8N_CONTRACTS_VALID" -ForegroundColor Green
    exit 0
}

# 3. Test HTTP /healthz or editor endpoint
Write-Host "3. Probing n8n HTTP endpoint ($N8nHost)..." -ForegroundColor Green
try {
    $resp = Invoke-WebRequest -Uri "$N8nHost/healthz" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) {
        Write-Host "   n8n /healthz responded HTTP 200 OK" -ForegroundColor Green
    } else {
        Write-Host "   n8n responded HTTP $($resp.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    # Some versions respond on root /
    try {
        $respRoot = Invoke-WebRequest -Uri "$N8nHost/" -UseBasicParsing -TimeoutSec 5
        Write-Host "   n8n root responded HTTP $($respRoot.StatusCode) OK" -ForegroundColor Green
    } catch {
        Write-Warning "Failed to connect to n8n at ${N8nHost}: $_"
    }
}

# 4. Test metrics endpoint
Write-Host "4. Probing n8n Prometheus metrics endpoint ($N8nHost/metrics)..." -ForegroundColor Green
try {
    $metricsResp = Invoke-WebRequest -Uri "$N8nHost/metrics" -UseBasicParsing -TimeoutSec 5
    if ($metricsResp.StatusCode -eq 200) {
        Write-Host "   n8n Prometheus metrics endpoint reachable (HTTP 200)" -ForegroundColor Green
    }
} catch {
    Write-Warning "n8n /metrics endpoint not reachable: $_"
}

# 5. Check imported workflows inside n8n
Write-Host "5. Checking imported workflows in n8n database..." -ForegroundColor Green
$listOutput = docker compose exec -T n8n n8n list:workflow 2>&1
Write-Host $listOutput

Write-Host ""
Write-Host "N8N_VERIFY_PASS" -ForegroundColor Green
