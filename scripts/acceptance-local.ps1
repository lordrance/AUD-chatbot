#requires -Version 5.1
<#
.SYNOPSIS
  SafeChat-AUD：本地 PostgreSQL 验收（Docker db + 从验收 env 加载 URL + Alembic + DB 集成测试）

.DESCRIPTION
  - 检查 Docker 是否可用并已启动
  - docker compose up -d db 并等待 pg_isready
  - 从仓库根目录 .env.acceptance（优先）或 .env.acceptance.example 读取 DATABASE_URL / TEST_DATABASE_URL
  - apps/api: alembic upgrade head
  - pytest test_safety_routes_integration + test_chat_flow_integration

  用法（仓库根目录）：
    .\scripts\acceptance-local.ps1
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot "docker-compose.yml"))) {
    Write-Host "ERROR: docker-compose.yml not found. Run this script from repo root:" -ForegroundColor Red
    Write-Host "  .\scripts\acceptance-local.ps1" -ForegroundColor Yellow
    exit 1
}

function Fail($msg) {
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit 1
}

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )
    $vars = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith("#")) { continue }
        $eq = $t.IndexOf("=")
        if ($eq -lt 1) { continue }
        $key = $t.Substring(0, $eq).Trim()
        $val = $t.Substring($eq + 1).Trim()
        if ($val.Length -ge 2 -and (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'")))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($key) { $vars[$key] = $val }
    }
    return $vars
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker CLI not found. Install Docker Desktop for Windows and ensure 'docker' is on PATH."
}

# docker info writes benign WARNING lines to stderr; with $ErrorActionPreference Stop that becomes a terminating error
# before LASTEXITCODE is reliable. Merge stderr into stdout and judge only by exit code.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker info 2>&1 | Out-Null
$dockerExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($dockerExit -ne 0) {
    Fail "Docker daemon not reachable (docker info exit code $dockerExit). Start Docker Desktop, wait until it is running (whale icon steady), then retry from a new terminal if needed."
}

$envAcceptance = Join-Path $RepoRoot ".env.acceptance"
$envExample = Join-Path $RepoRoot ".env.acceptance.example"
$envPath = $null
if (Test-Path -LiteralPath $envAcceptance) {
    $envPath = $envAcceptance
    Write-Host "==> Loading env from .env.acceptance" -ForegroundColor Cyan
}
elseif (Test-Path -LiteralPath $envExample) {
    $envPath = $envExample
    Write-Host "==> Loading env from .env.acceptance.example (optional: Copy-Item .env.acceptance.example .env.acceptance)" -ForegroundColor Cyan
}
else {
    Fail "No acceptance env file at repo root. Expected ``$envAcceptance`` or ``$envExample``. Restore the repo file ``.env.acceptance.example`` or copy it to ``.env.acceptance``."
}

$parsed = Import-DotEnvFile -Path $envPath
$dbRaw = $parsed["DATABASE_URL"]
$dbUrl = if ($null -eq $dbRaw) { "" } else { "$dbRaw".Trim() }
$testRaw = $parsed["TEST_DATABASE_URL"]
$testUrl = if ($null -eq $testRaw) { "" } else { "$testRaw".Trim() }
if (-not $dbUrl) {
    Fail "DATABASE_URL missing or empty in $envPath. Add a line like: DATABASE_URL=postgresql+psycopg://safechat:safechat@127.0.0.1:5432/safechat_aud"
}
if (-not $testUrl) {
    $testUrl = $dbUrl
    Write-Host "==> TEST_DATABASE_URL not set in file; using DATABASE_URL for both." -ForegroundColor Yellow
}

Set-Location $RepoRoot

Write-Host "==> Starting PostgreSQL (docker compose service 'db')..." -ForegroundColor Cyan
docker compose up -d db
if ($LASTEXITCODE -ne 0) {
    Fail "docker compose up -d db failed. From repo root ($RepoRoot), run: docker compose config"
}

Write-Host "==> Waiting for PostgreSQL (pg_isready, up to 120s)..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    docker compose exec -T db pg_isready -U safechat -d safechat_aud 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Fail "PostgreSQL did not become ready within 120s. Next: docker compose ps   docker compose logs db   Ensure port 5432 is free on the host (no other Postgres bound to 127.0.0.1:5432)."
}

$env:DATABASE_URL = $dbUrl
$env:TEST_DATABASE_URL = $testUrl
Write-Host "==> DATABASE_URL / TEST_DATABASE_URL applied from env file (running pytest with TEST_DATABASE_URL -> DATABASE_URL sync in conftest)" -ForegroundColor Cyan

$ApiDir = Join-Path $RepoRoot "apps\api"
Set-Location $ApiDir

$alembic = Join-Path $ApiDir ".venv\Scripts\alembic.exe"
$python = Join-Path $ApiDir ".venv\Scripts\python.exe"
if (-not (Test-Path $alembic)) {
    Fail "Missing $alembic. From repo root: cd apps\api; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

Write-Host "==> alembic heads (expect single head)..." -ForegroundColor Cyan
& $alembic heads
if ($LASTEXITCODE -ne 0) { Fail "alembic heads failed. Check DATABASE_URL in your env file matches docker-compose db (host 127.0.0.1:5432)." }

Write-Host "==> alembic upgrade head..." -ForegroundColor Cyan
& $alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Fail "alembic upgrade head failed. Verify: (1) DB is reachable at the host/port in DATABASE_URL, (2) user/password/database match POSTGRES_* in docker-compose.yml, (3) apps/api uses the same URL."
}

Write-Host "==> pytest DB-backed integration..." -ForegroundColor Cyan
& $python -m pytest tests/test_safety_routes_integration.py tests/test_chat_flow_integration.py -v --tb=short
$pyExit = $LASTEXITCODE

Set-Location $RepoRoot
if ($pyExit -ne 0) {
    Fail "pytest exited with code $pyExit. See failures above; checklist: docs/acceptance-checklist.md"
}

Write-Host "==> Acceptance OK (migrations applied + integration tests passed)." -ForegroundColor Green
exit 0
