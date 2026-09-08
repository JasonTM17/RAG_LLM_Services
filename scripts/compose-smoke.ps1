$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Assert-PortFree {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connection) {
        throw "Port $Port is already in use"
    }
}

function Assert-NoExistingRagContainers {
    $existing = docker ps -a --filter "name=rag_" --format "{{.Names}}"
    if ($existing) {
        throw "Existing rag_* containers found; refusing to touch possible user runtime state"
    }
}

function Wait-HealthyContainer {
    param(
        [string]$Name,
        [int]$TimeoutSeconds = 120
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = docker inspect -f "{{.State.Health.Status}}" $Name 2>$null
        if ($status -eq "healthy") {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Container $Name did not become healthy"
}

function Wait-HttpStatus {
    param(
        [string]$Url,
        [int]$ExpectedStatus = 200,
        [int]$TimeoutSeconds = 120
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ([int]$response.StatusCode -eq $ExpectedStatus) {
                return $response
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "Timed out waiting for $Url"
}

function Invoke-JsonPost {
    param(
        [string]$Url,
        [hashtable]$Body,
        [hashtable]$Headers
    )
    $json = $Body | ConvertTo-Json -Depth 12
    return Invoke-RestMethod `
        -Uri $Url `
        -Method Post `
        -Headers $Headers `
        -ContentType "application/json" `
        -Body $json `
        -TimeoutSec 30
}

function Wait-IngestionIndexed {
    param(
        [string]$ApiBase,
        [string]$JobId,
        [hashtable]$Headers
    )
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        $job = Invoke-RestMethod `
            -Uri "$ApiBase/api/v1/ingestion-jobs/$JobId" `
            -Headers $Headers `
            -TimeoutSec 10
        if ($job.status -eq "INDEXED") {
            return $job
        }
        if ($job.status -eq "FAILED") {
            throw "Ingestion job failed"
        }
        Start-Sleep -Seconds 3
    }
    throw "Ingestion job did not reach INDEXED"
}

function Wait-PrometheusTargets {
    param([string]$PrometheusBase)
    $required = @("rag-api", "rag-worker", "n8n", "postgres-exporter", "redis-exporter")
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $targets = Invoke-RestMethod -Uri "$PrometheusBase/api/v1/targets" -TimeoutSec 10
        $healthy = @{}
        foreach ($target in $targets.data.activeTargets) {
            if ($target.health -eq "up") {
                $healthy[$target.labels.job] = $true
            }
        }
        $missing = @($required | Where-Object { -not $healthy.ContainsKey($_) })
        if ($missing.Count -eq 0) {
            return
        }
        Start-Sleep -Seconds 5
    }
    throw "Prometheus targets did not become healthy"
}

function Test-GrafanaProvisioning {
    param([string]$GrafanaBase)
    $pair = [Convert]::ToBase64String(
        [Text.Encoding]::ASCII.GetBytes("admin:replace-with-local-grafana-password")
    )
    $headers = @{ Authorization = "Basic $pair" }
    $datasource = Invoke-RestMethod `
        -Uri "$GrafanaBase/api/datasources/name/Prometheus" `
        -Headers $headers `
        -TimeoutSec 10
    if ($datasource.uid -ne "prometheus") {
        throw "Grafana Prometheus datasource was not provisioned"
    }
    $dashboards = Invoke-RestMethod `
        -Uri "$GrafanaBase/api/search?type=dash-db" `
        -Headers $headers `
        -TimeoutSec 10
    if (($dashboards | Measure-Object).Count -lt 6) {
        throw "Grafana dashboard provisioning returned fewer than six dashboards"
    }
}

Assert-Command docker
Assert-Command curl.exe
Assert-NoExistingRagContainers

@(
    8000,
    3001,
    15432,
    16379,
    19000,
    19001,
    15678,
    19090,
    13000,
    19187,
    19121,
    19108
) | ForEach-Object { Assert-PortFree $_ }

$script:ComposeProject = "rag_phase16_smoke_$PID"
$env:APP_ENV = "local"
$env:API_PORT = "8000"
$env:POSTGRES_PORT = "15432"
$env:REDIS_PORT = "16379"
$env:MINIO_PORT = "19000"
$env:MINIO_CONSOLE_PORT = "19001"
$env:N8N_PORT = "15678"
$env:PROMETHEUS_PORT = "19090"
$env:GRAFANA_PORT = "13000"
$env:WEB_PORT = "3001"
$env:POSTGRES_EXPORTER_PORT = "19187"
$env:REDIS_EXPORTER_PORT = "19121"
$env:WORKER_METRICS_HOST_PORT = "19108"
$env:LLM_PROVIDER = "fake"
$env:RUN_DEEPSEEK_LIVE_TESTS = "false"
$env:EMBEDDING_PROVIDER = "fake"
$env:RERANKER_PROVIDER = "fake"
$env:RAG_BACKEND_ORIGIN = "http://api:8000"
$env:OPENAI_TRACING_DISABLED = "true"

$apiBase = "http://localhost:8000"
$prometheusBase = "http://localhost:19090"
$grafanaBase = "http://localhost:13000"
$headers = @{
    "X-User-Id" = "00000000-0000-0000-0000-000000000001"
    "X-Request-Id" = "phase-16-compose-smoke"
}
$tmpFile = $null

try {
    docker compose -p $script:ComposeProject --env-file .env.example up -d postgres redis minio minio-create-bucket
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose core up failed"
    }
    Wait-HealthyContainer "rag_postgres"
    Wait-HealthyContainer "rag_redis"
    Wait-HealthyContainer "rag_minio"

    docker compose -p $script:ComposeProject --env-file .env.example --profile api up -d --build api
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose api up failed"
    }
    Wait-HttpStatus "$apiBase/health/live" | Out-Null
    docker compose -p $script:ComposeProject --env-file .env.example exec -T api alembic -c apps/api/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade failed"
    }
    Wait-HttpStatus "$apiBase/health/ready" | Out-Null

    docker compose -p $script:ComposeProject --env-file .env.example --profile worker up -d --build worker
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose worker up failed"
    }
    docker compose -p $script:ComposeProject --env-file .env.example up -d n8n
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose n8n up failed"
    }
    docker compose -p $script:ComposeProject --env-file .env.example --profile observability up -d prometheus grafana
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose observability up failed"
    }
    docker compose -p $script:ComposeProject --env-file .env.example --profile api --profile web up -d --build web
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose web up failed"
    }

    Wait-HttpStatus "http://localhost:3001" -TimeoutSeconds 240 | Out-Null
    Wait-HttpStatus "$prometheusBase/-/ready" | Out-Null
    Wait-HttpStatus "$grafanaBase/api/health" | Out-Null

    $kb = Invoke-JsonPost `
        -Url "$apiBase/api/v1/knowledge-bases" `
        -Headers $headers `
        -Body @{
            name = "Compose Smoke KB"
            description = "Fixture-safe compose release smoke test"
        }

    $tmpFile = New-TemporaryFile
    Set-Content `
        -LiteralPath $tmpFile.FullName `
        -Value "# Compose Smoke`n`nHybrid retrieval and citations work through the compose API." `
        -Encoding UTF8
    $uploadRaw = curl.exe `
        -sS `
        -X POST "$apiBase/api/v1/documents" `
        -H "X-User-Id: $($headers['X-User-Id'])" `
        -H "X-Request-Id: $($headers['X-Request-Id'])" `
        -F "knowledge_base_id=$($kb.id)" `
        -F "file=@$($tmpFile.FullName);type=text/markdown;filename=compose-smoke.md"
    if ($LASTEXITCODE -ne 0) {
        throw "document upload curl request failed"
    }
    $upload = $uploadRaw | ConvertFrom-Json
    $job = Wait-IngestionIndexed -ApiBase $apiBase -JobId $upload.ingestion_job_id -Headers $headers

    $retrieval = Invoke-JsonPost `
        -Url "$apiBase/api/v1/retrieval/search" `
        -Headers $headers `
        -Body @{
            query = "hybrid retrieval citations"
            method = "hybrid"
            filter = @{ knowledge_base_id = $kb.id }
            include_context_bundle = $true
        }
    if ($retrieval.total_results -lt 1) {
        throw "compose retrieval returned no results"
    }

    $chat = Invoke-JsonPost `
        -Url "$apiBase/api/v1/chat" `
        -Headers $headers `
        -Body @{
            message = "Explain hybrid retrieval with one citation."
            knowledge_base_id = $kb.id
        }
    if ($chat.provider -ne "fake" -or $chat.citations[0].source_id -ne "[S1]") {
        throw "compose chat did not return fake cited answer"
    }

    $metrics = Invoke-WebRequest -Uri "$apiBase/metrics" -UseBasicParsing -TimeoutSec 10
    if (-not $metrics.Content.Contains("rag_http_requests_total")) {
        throw "API metrics did not expose HTTP request counter"
    }

    Wait-PrometheusTargets $prometheusBase
    Test-GrafanaProvisioning $grafanaBase

    $summary = [ordered]@{
        status = "PASS"
        api = "healthy"
        ready = "healthy"
        web = "started"
        worker_job_status = $job.status
        retrieval_results = $retrieval.total_results
        chat_provider = $chat.provider
        citation = $chat.citations[0].source_id
        prometheus_targets = "up"
        grafana_dashboards = "provisioned"
        live_deepseek = "NOT_RUN"
    }
    $summary | ConvertTo-Json -Depth 6
    Write-Host "COMPOSE_SMOKE_PASS"
}
finally {
    if ($tmpFile -and (Test-Path -LiteralPath $tmpFile.FullName)) {
        Remove-Item -LiteralPath $tmpFile.FullName -Force
    }
    & docker compose `
        -p $script:ComposeProject `
        --env-file .env.example `
        --profile api `
        --profile worker `
        --profile web `
        --profile observability `
        down --volumes --remove-orphans
}
