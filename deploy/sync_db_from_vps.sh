#!/usr/bin/env bash
# Pull production SQLite from VPS (checkpoint WAL first so the file is self-contained).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET="${DEPLOY_HOST:-root@31.97.186.20}"
REMOTE_DB="${REMOTE_DB:-/root/vernika/backend/data/vernika.db}"
LOCAL_DB="${ROOT_DIR}/backend/data/vernika.db"

mkdir -p "$(dirname "${LOCAL_DB}")"
ssh "${TARGET}" "/root/vernika/venv/bin/python3 -c \"
import sqlite3
c = sqlite3.connect('${REMOTE_DB}')
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.close()
\""
rm -f "${LOCAL_DB}" "${LOCAL_DB}-wal" "${LOCAL_DB}-shm"
scp "${TARGET}:${REMOTE_DB}" "${LOCAL_DB}"
echo "✅ Synced → ${LOCAL_DB} ($(wc -c < "${LOCAL_DB}" | tr -d ' ') bytes)"
