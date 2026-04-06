#requires -Version 5.1
<#
.SYNOPSIS
  10-session Gemini 冒烟：前 5 个 persona × 2 臂 × 每臂 1 次，经 eval/run_batch.py（真实 DB + TestClient）。

.DESCRIPTION
  请在仓库根目录执行。需：
  - Docker Postgres 或已设置的 DATABASE_URL
  - apps/api/.env 或当前会话中：LLM_PROVIDER=gemini、GEMINI_API_KEY=...

  用法：
    cd E:\ADU
    .\eval\smoke_gemini_10.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "缺少 $py — 先在 apps\api 创建 .venv 并 pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# 从 apps/api/.env 注入到当前进程（若存在）
$envFile = Join-Path $Root "apps\api\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2].Trim()
        }
    }
}

if (-not $env:DATABASE_URL -and -not $env:TEST_DATABASE_URL) {
    Write-Host "请设置 DATABASE_URL（或 TEST_DATABASE_URL）指向已 migrate 的 PostgreSQL。" -ForegroundColor Red
    exit 2
}

$provRaw = $env:LLM_PROVIDER
if (-not $provRaw) { $provRaw = "openai" }
$prov = $provRaw.ToLowerInvariant()
if ($prov -eq "gemini") {
    if (-not $env:GEMINI_API_KEY) {
        Write-Host "LLM_PROVIDER=gemini 时请设置 GEMINI_API_KEY（写在 apps\api\.env）。" -ForegroundColor Red
        exit 2
    }
} else {
    if (-not $env:OPENAI_API_KEY) {
        Write-Host "LLM_PROVIDER=openai 时请设置 OPENAI_API_KEY（或将 LLM_PROVIDER=gemini 并设置 GEMINI_API_KEY）。" -ForegroundColor Red
        exit 2
    }
    $buRaw = $env:OPENAI_BASE_URL
    if (-not $buRaw) { $buRaw = "" }
    $bu = $buRaw.ToLowerInvariant()
    if ($bu -like "*generativelanguage.googleapis.com*") {
        Write-Host "检测到 OPENAI_BASE_URL 指向 Gemini 兼容端点（合法旧写法）；推荐迁移为 LLM_PROVIDER=gemini + GEMINI_API_KEY。" -ForegroundColor Cyan
    }
}

$outDir = Join-Path $Root "eval\output\smoke_gemini_10_$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))"
& $py (Join-Path $Root "eval\run_batch.py") `
    --no-stub-llm `
    --runs-per-arm 1 `
    --max-personas 5 `
    --prompt-bundle-version 0.2.1 `
    --output $outDir

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $py (Join-Path $Root "eval\summarize_smoke_batch.py") --batch-dir $outDir
Write-Host "完成。摘要: $(Join-Path $outDir 'smoke_summary.md')" -ForegroundColor Green
