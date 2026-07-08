#!/usr/bin/env bash
# Bridge server only — run from repo root
set -e
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"

if [ ! -f ".env" ]; then
    echo "⚠️  Copy .env.example to .env and set keys."
    exit 1
fi

# Avoid silent failure when Docker already bound this port or another uvicorn runs.
_port_in_use() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -i TCP:"$PORT" -sTCP:LISTEN -P -n >/dev/null 2>&1
    elif command -v ss >/dev/null 2>&1; then
        ss -ltn "( sport = :$PORT )" 2>/dev/null | grep -q LISTEN
    else
        return 1
    fi
}
if _port_in_use; then
    echo "⚠️  Port $PORT is already in use."
    echo "   If Vernika is in Docker:  docker compose down   (or: docker stop vernika-bridge)"
    echo "   Or pick another port:     PORT=8001 ./start.sh"
    exit 1
fi

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

VENV_PY="$(pwd)/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "⚠️  venv/python missing — remove ./venv and re-run ./start.sh"
    exit 1
fi

"$VENV_PY" -m pip install -q -r requirements.txt

mkdir -p backend/data/data_edge

cd backend
export PYTHONPATH="."
if [ "${1:-}" = "dev" ]; then
  exec "$VENV_PY" -m uvicorn main:app --reload --host 0.0.0.0 --port "$PORT"
fi
exec "$VENV_PY" -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
