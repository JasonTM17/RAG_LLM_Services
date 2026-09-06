$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$expectedOrigin = "https://github.com/JasonTM17/RAG_LLM_Services.git"
$planDir = "plans/260906-2101-rag-llm-services-production-platform"

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Assert-PathExists {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Missing required path: $Path"
    }
}

Assert-Command git
Assert-Command rg
Assert-Command ak

$gitRoot = (& git rev-parse --show-toplevel).Trim()
if (-not $gitRoot) {
    throw "Not inside a Git repository"
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne "main") {
    throw "Expected branch main, got $branch"
}

$origin = (& git remote get-url origin).Trim()
if ($origin -ne $expectedOrigin) {
    throw "Expected origin $expectedOrigin, got $origin"
}

& git check-ignore -v .env | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw ".env is not ignored"
}

@(
    ".gitignore",
    ".gitattributes",
    ".env.example",
    ".python-version",
    ".node-version",
    "README.md",
    "CONTRIBUTING.md",
    "Makefile",
    "docs/architecture/system-overview.md",
    "docs/architecture/repository-structure.md",
    "docs/deployment/docker.md",
    "docs/security/threat-model.md",
    "docs/adr/ADR-001-postgres-pgvector.md",
    "docs/adr/ADR-002-bge-m3-embeddings.md",
    "docs/adr/ADR-003-hybrid-retrieval.md",
    "docs/adr/ADR-004-openai-agents-sdk-deepseek-provider.md",
    "docs/adr/ADR-005-n8n-orchestration.md",
    "docs/adr/ADR-006-redis-worker-architecture.md",
    "$planDir/plan.md",
    "$planDir/appendix-production-operating-model.md"
) | ForEach-Object { Assert-PathExists $_ }

& ak plan validate $planDir --no-interactive | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "AgentKit plan validation failed"
}

& rg -n --hidden --pcre2 "sk-[A-Za-z0-9]{20,}|gh[po]_[A-Za-z0-9]{30,}|Bearer\s+(sk|gh[po]_)[A-Za-z0-9._\-]{20,}" . `
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

& git diff --check | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "git diff --check failed"
}

Write-Host "PHASE_01_VERIFY_PASS"
