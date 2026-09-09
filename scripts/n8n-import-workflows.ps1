[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$StartIfStopped
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

Write-Host "=== n8n Workflow Auto-Provisioning ===" -ForegroundColor Cyan

# 1. Check if n8n container is running
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
    if ($StartIfStopped) {
        Write-Host "n8n service is not running. Attempting to start n8n service..." -ForegroundColor Yellow
        try {
            & docker compose up -d redis n8n
            Start-Sleep -Seconds 5
        } catch {
            Write-Error "Failed to start Docker Compose services: $_"
            exit 1
        }
    } else {
        Write-Host "WARNING: n8n service ('rag_n8n') is not currently running." -ForegroundColor Yellow
        Write-Host "Make sure Docker daemon is started, then run 'docker compose up -d redis n8n' before importing." -ForegroundColor Gray
        exit 1
    }
}

# 2. Execute n8n CLI workflow import from inside container
Write-Host "Importing workflows from /workflows into n8n..." -ForegroundColor Green
$importOutput = docker compose exec -T n8n n8n import:workflow --separate --input=/workflows 2>&1
Write-Host $importOutput

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to import workflows into n8n."
    exit 1
}

Write-Host ""
Write-Host "SUCCESS: 5 source-controlled n8n workflows imported into n8n successfully!" -ForegroundColor Green
Write-Host "Workflows available at: http://localhost:5678" -ForegroundColor Cyan
Write-Host "Imported workflows:" -ForegroundColor Gray
Write-Host "  1. RAG - Document Ingestion Orchestrator"
Write-Host "  2. RAG - Scheduled Knowledge Sync"
Write-Host "  3. RAG - Nightly RAG Evaluation"
Write-Host "  4. RAG - Daily Study Automation"
Write-Host "  5. RAG - Failure Notification"
