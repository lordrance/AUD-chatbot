#requires -Version 5.1
<#
.SYNOPSIS
  在仓库根目录创建 .venv 目录联接，指向 apps\api\.venv（仅 Windows）。

.DESCRIPTION
  创建后可在仓库根目录使用你习惯的命令：
    .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  须先完成：cd apps\api ; python -m venv .venv ; pip install -r requirements.txt

  用法（仓库根目录）：
    .\scripts\link-api-venv-to-root.ps1
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $RepoRoot "apps\api\.venv"
$Link = Join-Path $RepoRoot ".venv"

if (-not (Test-Path $Target)) {
    Write-Host "ERROR: Missing $Target — create venv in apps\api first." -ForegroundColor Red
    exit 1
}
if (Test-Path $Link) {
    Write-Host "ERROR: Already exists: $Link" -ForegroundColor Red
    Write-Host "Remove it first if you want to replace with a junction." -ForegroundColor Yellow
    exit 1
}

# Directory junction (no admin needed on same volume for mklink /J)
$cmd = "mklink /J `"$Link`" `"$Target`""
cmd /c $cmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: mklink failed (exit $LASTEXITCODE). Try running PowerShell as Administrator." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "OK: $Link -> $Target" -ForegroundColor Green
Write-Host "You can now run from repo root, e.g.:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000" -ForegroundColor Gray
