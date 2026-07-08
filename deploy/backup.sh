#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DB_SRC="backend/data/vernika.db"
SECRET_SRC="backend/data/.jwt_secret"
BACKUP_DIR="backend/data/backups"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)

if [ -f "$DB_SRC" ]; then
    cp "$DB_SRC" "$BACKUP_DIR/vernika-${TIMESTAMP}.db"
fi

if [ -f "$SECRET_SRC" ]; then
    cp "$SECRET_SRC" "$BACKUP_DIR/.jwt_secret-${TIMESTAMP}"
fi

# Rotate: keep only the last 14 backups
ls -1t "$BACKUP_DIR"/vernika-*.db 2>/dev/null | tail -n +15 | while read -r f; do
    rm -f "$f"
    ts=$(basename "$f" .db | sed 's/^vernika-//')
    rm -f "$BACKUP_DIR/.jwt_secret-${ts}"
done

# Optional remote sync
if [ -n "${BACKUP_REMOTE:-}" ]; then
    rsync -avz --delete "$BACKUP_DIR/" "$BACKUP_REMOTE"
fi
