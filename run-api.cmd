@echo off
setlocal
REM Start API from repo root (venv is under apps\api\.venv — not repo-root .venv).
cd /d "%~dp0apps\api"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Missing apps\api\.venv\Scripts\python.exe
  echo Create venv:  cd apps\api
  echo               python -m venv .venv
  echo               .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
echo Using: %CD%\.venv\Scripts\python.exe
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 %*
