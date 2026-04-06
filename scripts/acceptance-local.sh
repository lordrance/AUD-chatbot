#!/usr/bin/env bash
# SafeChat-AUD: local PostgreSQL acceptance (Docker db + env file + Alembic + integration pytest)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f docker-compose.yml ]]; then
  echo "ERROR: run from repo root (docker-compose.yml missing)" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not reachable. Start Docker and retry." >&2
  exit 1
fi

ENV_FILE=""
if [[ -f "$ROOT/.env.acceptance" ]]; then
  ENV_FILE="$ROOT/.env.acceptance"
  echo "==> Loading env from .env.acceptance"
elif [[ -f "$ROOT/.env.acceptance.example" ]]; then
  ENV_FILE="$ROOT/.env.acceptance.example"
  echo "==> Loading env from .env.acceptance.example (optional: cp .env.acceptance.example .env.acceptance)"
else
  echo "ERROR: No .env.acceptance or .env.acceptance.example at repo root ($ROOT)" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source <(sed 's/\r$//' "$ENV_FILE")
set +a

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL missing or empty in $ENV_FILE" >&2
  exit 1
fi
if [[ -z "${TEST_DATABASE_URL:-}" ]]; then
  export TEST_DATABASE_URL="$DATABASE_URL"
  echo "==> TEST_DATABASE_URL not set in file; using DATABASE_URL"
fi

echo "==> Starting PostgreSQL (docker compose service db)..."
docker compose up -d db

echo "==> Waiting for pg_isready (up to 120s)..."
for i in $(seq 1 120); do
  if docker compose exec -T db pg_isready -U safechat -d safechat_aud >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [[ "$i" -eq 120 ]]; then
    echo "ERROR: PostgreSQL not ready in 120s. Next: docker compose ps && docker compose logs db (check host port 5432)" >&2
    exit 1
  fi
done

cd "$ROOT/apps/api"
if [[ ! -f .venv/bin/alembic ]]; then
  echo "ERROR: apps/api/.venv missing. Run: cd apps/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "==> alembic heads"
.venv/bin/alembic heads
echo "==> alembic upgrade head"
.venv/bin/alembic upgrade head

echo "==> pytest integration"
.venv/bin/python -m pytest tests/test_safety_routes_integration.py tests/test_chat_flow_integration.py -v --tb=short

echo "==> Acceptance OK"
exit 0
