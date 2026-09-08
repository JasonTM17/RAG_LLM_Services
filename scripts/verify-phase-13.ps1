$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$planDir = "plans/260906-2101-rag-llm-services-production-platform"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Assert-NoMatches {
    param(
        [string]$Pattern,
        [string[]]$Paths,
        [string]$FailureMessage,
        [string[]]$ExtraArgs = @()
    )
    $args = @("-n", "--hidden", "--pcre2", $Pattern) + $Paths + $ExtraArgs
    & rg @args
    if ($LASTEXITCODE -eq 0) {
        throw $FailureMessage
    }
    if ($LASTEXITCODE -gt 1) {
        throw "$FailureMessage (scan command failed)"
    }
}

Assert-Command git
Assert-Command uv
Assert-Command rg
Assert-Command docker
Assert-Command node
Assert-Command pnpm

$gitRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $gitRoot) {
    throw "Not inside a Git repository"
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne "main" -and -not $branch.StartsWith("feat/")) {
    throw "Expected branch main or a feat/ branch, got $branch"
}

$nodeVersion = (& node --version).Trim()
if ($nodeVersion -ne "v24.12.0") {
    throw "Expected Node v24.12.0, got $nodeVersion"
}

$pnpmVersion = (& pnpm --version).Trim()
if ($pnpmVersion -ne "11.0.9") {
    throw "Expected pnpm 11.0.9, got $pnpmVersion"
}

@(
    "package.json",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
    "apps/web/package.json",
    "apps/web/next.config.ts",
    "apps/web/tsconfig.json",
    "apps/web/eslint.config.mjs",
    "apps/web/vitest.config.ts",
    "apps/web/playwright.config.ts",
    "apps/web/app/layout.tsx",
    "apps/web/app/page.tsx",
    "apps/web/app/chat/page.tsx",
    "apps/web/app/documents/page.tsx",
    "apps/web/app/knowledge-bases/page.tsx",
    "apps/web/app/study/page.tsx",
    "apps/web/app/system-status/page.tsx",
    "apps/web/components/chat/chat-workspace.tsx",
    "apps/web/components/documents/documents-workspace.tsx",
    "apps/web/components/knowledge-bases/knowledge-base-workspace.tsx",
    "apps/web/components/study/study-workspace.tsx",
    "apps/web/components/status/system-status-workspace.tsx",
    "apps/web/components/ui/citations.tsx",
    "apps/web/components/ui/status-badge.tsx",
    "apps/web/lib/api-client.ts",
    "apps/web/lib/types.ts",
    "apps/web/lib/fixtures.ts",
    "apps/web/tests/api-client.spec.ts",
    "apps/web/tests/chat-workspace.spec.tsx",
    "apps/web/tests/documents-workspace.spec.tsx",
    "tests/e2e/upload-chat-citation.spec.ts",
    "docs/frontend/web-app.md",
    "docker-compose.yml",
    "$planDir/phase-13-frontend-application.md"
) | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) {
        throw "Missing required path: $_"
    }
}

pnpm install --frozen-lockfile
if ($LASTEXITCODE -ne 0) {
    throw "pnpm install failed"
}

pnpm web:lint
if ($LASTEXITCODE -ne 0) {
    throw "frontend lint failed"
}

pnpm web:typecheck
if ($LASTEXITCODE -ne 0) {
    throw "frontend typecheck failed"
}

pnpm web:test
if ($LASTEXITCODE -ne 0) {
    throw "frontend unit/component tests failed"
}

pnpm web:build
if ($LASTEXITCODE -ne 0) {
    throw "frontend build failed"
}

$systemBrowser = $null
$isWindowsHost = $env:OS -eq "Windows_NT" -or [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)
if ($isWindowsHost) {
    $browserCandidates = @(
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
    foreach ($candidate in $browserCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            $systemBrowser = $candidate
            break
        }
    }
}
if ($systemBrowser) {
    Write-Host "PLAYWRIGHT_SYSTEM_BROWSER: $systemBrowser"
} else {
    pnpm --filter "@rag-llm-services/web" exec playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright Chromium install failed"
    }
}

if (-not $env:WEB_E2E_PORT) {
    $env:WEB_E2E_PORT = "43117"
}
Write-Host "WEB_E2E_PORT: $env:WEB_E2E_PORT"

pnpm web:e2e
if ($LASTEXITCODE -ne 0) {
    throw "frontend e2e tests failed"
}

docker compose --profile web config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "docker compose web config failed"
}

uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed"
}

uv run pytest -q tests/integration/documents/test_document_api.py::test_document_upload_lifecycle tests/integration/llm/test_chat_mocked.py::test_chat_stream_endpoint_uses_semantic_events_without_done_sentinel
if ($LASTEXITCODE -ne 0) {
    throw "backend frontend contract regressions failed"
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

$secretPattern = "sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}"
Assert-NoMatches `
    -Pattern $secretPattern `
    -Paths @(".") `
    -FailureMessage "Credential-shaped material detected outside local env files" `
    -ExtraArgs @(
        "-g", "!**/.env",
        "-g", "!**/.git/**",
        "-g", "!**/node_modules/**",
        "-g", "!**/.venv/**",
        "-g", "!**/.next/**"
    )

Assert-NoMatches `
    -Pattern "NEXT_PUBLIC|DEEPSEEK_API_KEY|N8N_API_KEY|GRAFANA_ADMIN_PASSWORD|MINIO_SECRET_KEY|POSTGRES_PASSWORD|DATABASE_URL" `
    -Paths @("apps/web") `
    -FailureMessage "Secret-bearing or public API env key found in frontend source" `
    -ExtraArgs @("-g", "!**/node_modules/**", "-g", "!**/.next/**")

if (Test-Path -LiteralPath "apps/web/.next/static") {
    Assert-NoMatches `
        -Pattern $secretPattern `
        -Paths @("apps/web/.next/static") `
        -FailureMessage "Credential-shaped material detected in frontend static bundle"
    Assert-NoMatches `
        -Pattern "DEEPSEEK_API_KEY|N8N_API_KEY|GRAFANA_ADMIN_PASSWORD|MINIO_SECRET_KEY|POSTGRES_PASSWORD|DATABASE_URL" `
        -Paths @("apps/web/.next/static") `
        -FailureMessage "Secret-bearing env key found in frontend static bundle"
}

git diff --check
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_13_VERIFY_PASS"
