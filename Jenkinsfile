pipeline {
  agent any

  options {
    timestamps()
    ansiColor('xterm')
  }

  environment {
    // Allow acceptance scripts to find repo root
    REPO_ROOT = "${WORKSPACE}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Backend unit tests (fast)') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              cd apps/api
              python -m venv .venv || true
              . .venv/bin/activate
              pip install -r requirements.txt
              python -m pytest -q
            '''
          } else {
            powershell '''
              $ErrorActionPreference = "Stop"
              Set-Location (Join-Path $env:WORKSPACE "apps\\api")
              if (-not (Test-Path ".venv")) { python -m venv .venv }
              .\\.venv\\Scripts\\Activate.ps1
              pip install -r requirements.txt
              python -m pytest -q
            '''
          }
        }
      }
    }

    stage('Acceptance (DB + migrations + integration)') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              cd "$WORKSPACE"
              chmod +x scripts/acceptance-local.sh || true
              ./scripts/acceptance-local.sh
            '''
          } else {
            powershell '''
              $ErrorActionPreference = "Stop"
              Set-Location $env:WORKSPACE
              powershell -ExecutionPolicy Bypass -File ".\\scripts\\acceptance-local.ps1"
            '''
          }
        }
      }
    }

    stage('Frontend build') {
      steps {
        script {
          if (isUnix()) {
            sh '''
              set -e
              cd apps/web
              npm ci || npm install
              npm run build
            '''
          } else {
            powershell '''
              $ErrorActionPreference = "Stop"
              Set-Location (Join-Path $env:WORKSPACE "apps\\web")
              if (Test-Path "package-lock.json") { npm ci } else { npm install }
              npm run build
            '''
          }
        }
      }
    }
  }
}

