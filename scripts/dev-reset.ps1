param(
    [switch]$UseIsolatedApiPort
)

$ErrorActionPreference = "Stop"

$RepoRoot = "E:\ADU"
$ApiDir = Join-Path $RepoRoot "apps\api"
$WebDir = Join-Path $RepoRoot "apps\web"
$ApiPort = if ($UseIsolatedApiPort) { 18000 } else { 8000 }

function Stop-DevProcesses {
    Write-Host "==> Stopping old uvicorn/vite processes..."

    $uvicorn = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match "python.exe" -and $_.CommandLine -match "uvicorn app.main:app"
    }
    foreach ($p in $uvicorn) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ("  stopped uvicorn PID {0}" -f $p.ProcessId)
        } catch {
            Write-Host ("  skip uvicorn PID {0}" -f $p.ProcessId)
        }
    }

    $vite = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match "node.exe" -and $_.CommandLine -match "vite"
    }
    foreach ($p in $vite) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ("  stopped vite PID {0}" -f $p.ProcessId)
        } catch {
            Write-Host ("  skip vite PID {0}" -f $p.ProcessId)
        }
    }
}

function Start-Db {
    Write-Host "==> Ensuring docker db is running..."
    Set-Location $RepoRoot
    docker compose up -d db | Out-Host
}

function Start-Api {
    Write-Host ("==> Starting API on http://127.0.0.1:{0}" -f $ApiPort)
    $apiCmd = "Set-Location `"$ApiDir`"; & `".\.venv\Scripts\python.exe`" -m uvicorn app.main:app --reload --host 127.0.0.1 --port $ApiPort"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd | Out-Null
}

function Start-Web {
    Write-Host "==> Starting web on http://localhost:5173"
    $webCmd = if ($UseIsolatedApiPort) {
        "Set-Location `"$WebDir`"; `$env:VITE_API_PROXY_TARGET=`"http://127.0.0.1:$ApiPort`"; npm run dev -- --port 5173 --strictPort"
    } else {
        "Set-Location `"$WebDir`"; Remove-Item Env:VITE_API_PROXY_TARGET -ErrorAction SilentlyContinue; npm run dev -- --port 5173 --strictPort"
    }
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd | Out-Null
}

Stop-DevProcesses
Start-Sleep -Milliseconds 600
Start-Db
Start-Api
Start-Web

Write-Host ""
Write-Host "Done."
Write-Host ("API: http://127.0.0.1:{0}/docs" -f $ApiPort)
Write-Host "Web: http://localhost:5173/"
if ($UseIsolatedApiPort) {
    Write-Host "Mode: isolated API port enabled."
}
