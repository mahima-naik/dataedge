#!/usr/bin/env bash
# Start the bridge in Docker from the repo root (handles missing .env and Docker daemon).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    echo "No .env — copying .env.example → .env (edit with your real keys)."
    cp .env.example .env
  else
    echo "Missing .env and .env.example. Create .env with at least GEMINI_API_KEY."
    exit 1
  fi
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running or this user cannot access the Docker socket."
  echo "Start Docker Desktop (or run: colima start) and try again."
  exit 1
fi

exec docker compose up --build "$@"
