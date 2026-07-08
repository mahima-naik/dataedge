#!/bin/bash
# Rollback script: Reverts the summary fix
# Restores original files from backup

BACKEND="/root/DataEdge/backend"

# Find the most recent backup
LATEST_BACKUP=$(ls -dt "$BACKEND"/.backup_fix_* 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "No backup found. Nothing to rollback."
    exit 1
fi

echo "=== Rolling back from: $LATEST_BACKUP ==="

if [ -f "$LATEST_BACKUP/local_analyzer.py.bak" ]; then
    cp "$LATEST_BACKUP/local_analyzer.py.bak" "$BACKEND/services/local_analyzer.py"
    echo "local_analyzer.py restored."
fi

if [ -f "$LATEST_BACKUP/config.py.bak" ]; then
    cp "$LATEST_BACKUP/config.py.bak" "$BACKEND/config.py"
    echo "config.py restored."
fi

echo ""
echo "=== Restarting dataedge service ==="
systemctl restart dataedge.service
echo "Service restarted."

echo ""
echo "=== ROLLBACK COMPLETE ==="
