#!/bin/bash
# VPS Fix Script: Update VAD sensitivity from BALANCED to LOW
# Run this on VPS: bash vps_fix_vad.sh

set -e

echo "=== VPS Fix: VAD Sensitivity Update ==="
echo ""

# Step 1: Backup current .env
echo "[1/4] Backing up current .env..."
if [ -f /root/app/.env ]; then
    cp /root/app/.env /root/app/.env.backup.$(date +%Y%m%d_%H%M%S)
    echo "  ✓ Backup created"
else
    echo "  ⚠ No .env found at /root/app/.env"
fi

# Step 2: Update VAD sensitivity values
echo "[2/4] Updating VAD sensitivity values..."
if [ -f /root/app/.env ]; then
    # Fix START_SENSITIVITY
    sed -i 's/GEMINI_LIVE_VAD_START_SENSITIVITY=START_SENSITIVITY_BALANCED/GEMINI_LIVE_VAD_START_SENSITIVITY=START_SENSITIVITY_HIGH/g' /root/app/.env
    sed -i 's/GEMINI_LIVE_VAD_START_SENSITIVITY=START_SENSITIVITY_LOW/GEMINI_LIVE_VAD_START_SENSITIVITY=START_SENSITIVITY_HIGH/g' /root/app/.env
    
    # Fix END_SENSITIVITY
    sed -i 's/GEMINI_LIVE_VAD_END_SENSITIVITY=END_SENSITIVITY_BALANCED/GEMINI_LIVE_VAD_END_SENSITIVITY=END_SENSITIVITY_HIGH/g' /root/app/.env
    sed -i 's/GEMINI_LIVE_VAD_END_SENSITIVITY=END_SENSITIVITY_LOW/GEMINI_LIVE_VAD_END_SENSITIVITY=END_SENSITIVITY_HIGH/g' /root/app/.env
    
    echo "  ✓ VAD sensitivity updated to HIGH"
    
    # Verify the changes
    echo ""
    echo "  Current VAD settings:"
    grep -E "GEMINI_LIVE_VAD_(START|END)_SENSITIVITY" /root/app/.env || echo "  (no VAD settings found)"
else
    echo "  ✗ Cannot update - .env not found"
    exit 1
fi

# Step 3: Verify recording directories exist
echo ""
echo "[3/4] Verifying recording directories..."
RECORDING_BASE="/root/app/data/recordings"
TODAY=$(date +%Y-%m-%d)

mkdir -p "${RECORDING_BASE}/${TODAY}"
echo "  ✓ Recording directory: ${RECORDING_BASE}/${TODAY}"

# Step 4: Restart service (optional - uncomment if needed)
echo ""
echo "[4/4] Service status check..."
if systemctl is-active --quiet vernika.service; then
    echo "  ✓ vernika.service is running"
    echo ""
    echo "To apply changes, restart the service:"
    echo "  sudo systemctl restart vernika.service"
    echo ""
    read -p "Restart service now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "  Restarting vernika.service..."
        sudo systemctl restart vernika.service
        sleep 2
        if systemctl is-active --quiet vernika.service; then
            echo "  ✓ Service restarted successfully"
        else
            echo "  ✗ Service failed to restart - check logs"
            sudo systemctl status vernika.service --no-pager
        fi
    else
        echo "  Skipped restart"
    fi
else
    echo "  ⚠ vernika.service not running"
fi

echo ""
echo "=== Fix Complete ==="
echo ""
echo "After restart, monitor logs for VAD changes:"
echo "  sudo journalctl -u vernika.service -f --since '1 min ago'"
echo ""
echo "Look for this line in logs:"
echo '  DIAG VAD config: ... start_sens=START_SENSITIVITY_HIGH end_sens=END_SENSITIVITY_HIGH ...'
