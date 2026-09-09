[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$DockerHubUser = $env:DOCKERHUB_USERNAME,

    [Parameter(Mandatory = $false)]
    [string]$Tag = "",

    [Parameter(Mandatory = $false)]
    [switch]$Push,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# 1. Determine Docker Hub Username
if (-not $DockerHubUser) {
    Write-Host "NOTE: DockerHubUser not provided. Defaulting to 'jasontm17' (repository owner)." -ForegroundColor Yellow
    $DockerHubUser = "jasontm17"
}

# 2. Determine Tag
if (-not $Tag) {
    $gitTag = git describe --tags --exact-match 2>$null
    if ($gitTag) {
        $Tag = $gitTag.Trim()
    } else {
        $commitSha = git rev-parse --short HEAD 2>$null
        if ($commitSha) {
            $Tag = "sha-$($commitSha.Trim())"
        } else {
            $Tag = "latest"
        }
    }
}

Write-Host "=== Docker Hub Image Publishing Automation ===" -ForegroundColor Cyan
Write-Host "Repository root: $repoRoot"
Write-Host "Docker Hub User: $DockerHubUser"
Write-Host "Image Tag:       $Tag"
Write-Host "Push to Hub:     $Push"
Write-Host "Dry Run Mode:    $DryRun"
Write-Host ""

$images = @(
    @{ Name = "api";    Dockerfile = "apps/api/Dockerfile";    HubRepo = "$DockerHubUser/rag-llm-services-api" },
    @{ Name = "worker"; Dockerfile = "apps/worker/Dockerfile"; HubRepo = "$DockerHubUser/rag-llm-services-worker" },
    @{ Name = "web";    Dockerfile = "apps/web/Dockerfile";    HubRepo = "$DockerHubUser/rag-llm-services-web" }
)

# 3. Pre-flight authentication check if pushing
if ($Push -and -not $DryRun) {
    $dockerInfo = (& docker info 2>&1)
    $loginCheck = $dockerInfo | Select-String -Pattern "^\s*Username:\s*(\S+)"
    if ($loginCheck) {
        $loggedUser = $loginCheck.Matches[0].Groups[1].Value
        Write-Host "Detected active Docker Hub session: $loggedUser" -ForegroundColor Green
    } else {
        Write-Warning "Docker Hub session not detected. If push fails with 'access denied', run: docker login -u $DockerHubUser"
    }
}

# 4. Build and tag each service
foreach ($img in $images) {
    $hubTag = "$($img.HubRepo):$Tag"
    $hubLatest = "$($img.HubRepo):latest"
    
    Write-Host "--- Processing $($img.Name) ---" -ForegroundColor Green
    $buildCmd = "docker build --pull -f $($img.Dockerfile) -t $hubTag -t $hubLatest $repoRoot"
    
    Write-Host "Executing build: $buildCmd"
    if (-not $DryRun) {
        Invoke-Expression $buildCmd
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to build $($img.Name)"
            exit 1
        }
    }

    if ($Push) {
        Write-Host "Pushing $hubTag..." -ForegroundColor Magenta
        $pushCmd1 = "docker push $hubTag"
        $pushCmd2 = "docker push $hubLatest"
        if (-not $DryRun) {
            Invoke-Expression $pushCmd1
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Failed to push $hubTag. Ensure you are logged into Docker Hub with write access: 'docker login -u $DockerHubUser'"
                exit 1
            }
            Invoke-Expression $pushCmd2
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Failed to push $hubLatest. Ensure you are logged into Docker Hub with write access: 'docker login -u $DockerHubUser'"
                exit 1
            }
        } else {
            Write-Host "[DryRun] $pushCmd1"
            Write-Host "[DryRun] $pushCmd2"
        }
    }
}

Write-Host ""
if ($Push) {
    Write-Host "SUCCESS: All images successfully built and pushed to Docker Hub!" -ForegroundColor Green
} else {
    Write-Host "SUCCESS: All images built and tagged locally! (Add -Push to upload to Docker Hub)" -ForegroundColor Yellow
}
