#!/bin/bash
# Deploy bridge layout → VPS (adjust host/path as needed)
# Remote WorkingDirectory for uvicorn should match RUNTIME (default: backend/).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"
TARGET="${DEPLOY_HOST:-root@31.97.186.20}"
REMOTE="${REMOTE_ROOT:-/root/vernika}"
RUNTIME="${RUNTIME_DIR:-backend}"

echo "🚀 Deploy → $TARGET:$REMOTE/$RUNTIME"
echo ""

echo "📦 Frontend"
if command -v rsync >/dev/null 2>&1; then
  rsync -az --exclude ".DS_Store" -e ssh "${ROOT_DIR}/frontend/" "${TARGET}:${REMOTE}/frontend/"
else
  scp -r "${ROOT_DIR}/frontend/" "${TARGET}:${REMOTE}/frontend/"
fi

echo "📦 Backend (api + core + services + entry)"
scp "${ROOT_DIR}/backend/main.py" "${ROOT_DIR}/backend/config.py" "${TARGET}:${REMOTE}/${RUNTIME}/"
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

echo "✅ Sync done."

# Transcript QA callback times (IST): ensure VPS env has Asian/Kolkata anchor.
ENV_ROOT="${REMOTE}/.env"
ENV_BACKEND="${REMOTE}/${RUNTIME}/.env"
for envpath in "${ENV_ROOT}" "${ENV_BACKEND}"; do
  ssh "${TARGET}" "if [ -f '${envpath}' ] && ! grep -q '^TRANSCRIPT_CALLBACK_TZ=' '${envpath}' 2>/dev/null; then echo 'TRANSCRIPT_CALLBACK_TZ=Asia/Kolkata' >> '${envpath}'; echo \"  appended TRANSCRIPT_CALLBACK_TZ → ${envpath}\"; fi" || true
done

# Avoid orphaned uvicorn holding :8000 while systemd restart loops (would serve stale API → 404 on newer routes).
echo "📦 Python deps (if requirements changed)"
ssh "${TARGET}" "${REMOTE}/venv/bin/pip install -r ${REMOTE}/${RUNTIME}/requirements.txt -q" || true

echo "🔁 Restart vernika.service (stop → free :8000 → start)"
ssh "${TARGET}" "systemctl stop vernika.service 2>/dev/null || true; sleep 1; fuser -k 8000/tcp 2>/dev/null || true; sleep 1; systemctl start vernika.service 2>/dev/null || systemctl restart vernika.service 2>/dev/null || true"
sleep 2
ssh "${TARGET}" "systemctl is-active vernika.service 2>/dev/null || true; curl -sf http://127.0.0.1:8000/health >/dev/null && echo '  health: ok' || echo '  health: FAILED — check server.log'"

echo "💡 On host if deps changed: ssh ${TARGET} 'cd ${REMOTE}/${RUNTIME} && pip install -r requirements.txt && systemctl restart vernika.service'"
