#!/bin/bash
# Deploy to the LIVE stack (Traefik → docker nginx → host :8001 → /root/DataEdge).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"
TARGET="${DEPLOY_HOST:-root@89.116.122.41}"
REMOTE="${REMOTE_ROOT:-/root/DataEdge}"
RUNTIME="${RUNTIME_DIR:-backend}"

echo "🚀 Deploy LIVE Data Edge → $TARGET:$REMOTE ($RUNTIME on :8001)"
echo ""

echo "📦 Frontend"
if command -v rsync >/dev/null 2>&1; then
  rsync -az --exclude ".DS_Store" -e ssh "${ROOT_DIR}/frontend/" "${TARGET}:${REMOTE}/frontend/"
else
  scp -r "${ROOT_DIR}/frontend/" "${TARGET}:${REMOTE}/frontend/"
fi

echo "📦 .env (config)"
scp "${ROOT_DIR}/.env" "${TARGET}:${REMOTE}/.env"

echo "📦 Backend"
scp "${ROOT_DIR}/backend/main.py" "${ROOT_DIR}/backend/config.py" "${ROOT_DIR}/backend/fix_websocket.py" "${TARGET}:${REMOTE}/${RUNTIME}/"
scp -r "${ROOT_DIR}/backend/api" "${TARGET}:${REMOTE}/${RUNTIME}/"
scp -r "${ROOT_DIR}/backend/core" "${TARGET}:${REMOTE}/${RUNTIME}/"
scp -r "${ROOT_DIR}/backend/services" "${TARGET}:${REMOTE}/${RUNTIME}/"
scp -r "${ROOT_DIR}/backend/scripts" "${TARGET}:${REMOTE}/${RUNTIME}/" 2>/dev/null || true
scp "${ROOT_DIR}/backend/requirements.txt" "${TARGET}:${REMOTE}/${RUNTIME}/"

echo "📦 Prompts + data snippets"
ssh "${TARGET}" "mkdir -p ${REMOTE}/${RUNTIME}/prompts ${REMOTE}/${RUNTIME}/data/{data_edge,greetings,background}"
scp "${ROOT_DIR}/backend/prompts/"*.txt "${TARGET}:${REMOTE}/${RUNTIME}/prompts/" 2>/dev/null || true
scp "${ROOT_DIR}/backend/prompts/"*.py "${TARGET}:${REMOTE}/${RUNTIME}/prompts/" 2>/dev/null || true
scp "${ROOT_DIR}/backend/data/data_edge/rag_source.txt" "${TARGET}:${REMOTE}/${RUNTIME}/data/data_edge/" 2>/dev/null || true
scp "${ROOT_DIR}/backend/data/background/"*.wav "${TARGET}:${REMOTE}/${RUNTIME}/data/background/" 2>/dev/null || true
scp "${ROOT_DIR}/backend/data/greetings/"*.pcm "${TARGET}:${REMOTE}/${RUNTIME}/data/greetings/" 2>/dev/null || true
scp "${ROOT_DIR}/backend/data/greetings/"*.pcm.meta "${TARGET}:${REMOTE}/${RUNTIME}/data/greetings/" 2>/dev/null || true

echo "📦 Python deps"
ssh "${TARGET}" "${REMOTE}/venv/bin/pip install -r ${REMOTE}/${RUNTIME}/requirements.txt -q" || true

echo "🔧 Run WebSocket fix (DB public_url + .env check)"
ssh "${TARGET}" "cd ${REMOTE}/${RUNTIME} && ${REMOTE}/venv/bin/python fix_websocket.py" || true

echo "🔓 Ensure port 8001 is accessible for WebSocket"
ssh "${TARGET}" "ufw allow 8001/tcp 2>/dev/null || iptables -A INPUT -p tcp --dport 8001 -j ACCEPT 2>/dev/null || echo '  (firewall not configured — skip)'" || true

echo "🔁 Restart dataedge.service (free :8001 first)"
ssh "${TARGET}" "systemctl stop dataedge.service 2>/dev/null || true; sleep 1; fuser -k 8001/tcp 2>/dev/null || true; pkill -f '[u]vicorn.*8001' 2>/dev/null || true; sleep 2; systemctl start dataedge.service"
sleep 3
ssh "${TARGET}" "systemctl is-active dataedge.service; curl -sf http://127.0.0.1:8001/health && echo ' health ok' || echo ' health FAILED'"

echo "✅ Live console: https://dataedge.srv1003582.hstgr.cloud/console"
