#!/bin/bash
# ── Data Edge VPS Deployment Script ──────────────────────────────────────
# Run this ON THE VPS as root to deploy the latest code and fix the
# crash-loop + WebSocket disconnect issues.
#
# Usage:
#   scp -r "Data-Edge (2) 2/Data-Edge" root@89.116.122.41:/opt/dataedge
#   ssh root@89.116.122.41 "bash /opt/dataedge/deploy/deploy_vps.sh"
# ──────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/dataedge"
BACKEND="$APP_DIR/backend"
VENV="$APP_DIR/venv"
LOG_DIR="/var/log/dataedge"
SERVICE_FILE="/etc/systemd/system/dataedge.service"

echo "═══════════════════════════════════════════════════════════════════"
echo "  Data Edge VPS Deployment — $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════════"

# 1. Stop existing service (if running)
echo ""
echo "▸ Stopping existing service..."
systemctl stop dataedge.service 2>/dev/null || true

# 2. Create log directory
echo "▸ Creating log directory..."
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"

# 3. Python venv + dependencies
echo "▸ Setting up Python virtual environment..."
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install --upgrade pip > /dev/null 2>&1

echo "▸ Installing dependencies..."
pip install -r "$BACKEND/requirements.txt" 2>&1 | tail -3

# Install uvloop + httptools for performance (optional but recommended)
pip install uvloop httptools 2>/dev/null || echo "  (uvloop/httptools not available — using defaults)"

# 4. Validate .env
echo "▸ Validating .env configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "  ⚠  WARNING: $APP_DIR/.env not found!"
    echo "     Copy your .env to $APP_DIR/.env and re-run this script."
    exit 1
fi

# Check critical vars
source "$APP_DIR/.env"
MISSING=""
[ -z "${GEMINI_API_KEY:-}" ] && MISSING="$MISSING GEMINI_API_KEY"
[ -z "${VOBIZ_PUBLIC_BASE_URL:-}" ] && MISSING="$MISSING VOBIZ_PUBLIC_BASE_URL"
[ -z "${VOBIZ_DATA_EDGE_AUTH_ID:-}" ] && MISSING="$MISSING VOBIZ_DATA_EDGE_AUTH_ID"

if [ -n "$MISSING" ]; then
    echo "  ⚠  WARNING: Missing critical env vars:$MISSING"
    echo "     Calls will fail until these are set."
fi

# Check for Hostinger domain in VOBIZ_PUBLIC_BASE_URL
if echo "${VOBIZ_PUBLIC_BASE_URL:-}" | grep -qi "hstgr.cloud"; then
    echo ""
    echo "  ⚠  ═══════════════════════════════════════════════════════════"
    echo "  ⚠  CRITICAL: VOBIZ_PUBLIC_BASE_URL uses Hostinger domain!"
    echo "  ⚠  Hostinger's proxy BLOCKS WebSocket upgrades (101)."
    echo "  ⚠  Calls will ring but produce SILENCE."
    echo "  ⚠  FIX: Set VOBIZ_PUBLIC_BASE_URL=http://89.116.122.41:8001"
    echo "  ⚠  FIX: Set VOBIZ_STREAM_PUBLIC_BASE_URL=http://89.116.122.41:8001"
    echo "  ⚠  ═══════════════════════════════════════════════════════════"
    echo ""
fi

# 5. Install systemd service
echo "▸ Installing systemd service..."
cat > "$SERVICE_FILE" << 'SERVICE_EOF'
[Unit]
Description=PitchX Solutions — Data Edge AI Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/dataedge/backend

StandardOutput=append:/var/log/dataedge/stdout.log
StandardError=append:/var/log/dataedge/stderr.log

ExecStart=/opt/dataedge/venv/bin/python -u -m uvicorn main:app \
    --host 0.0.0.0 --port 8001 \
    --workers 1 \
    --loop uvloop \
    --http httptools \
    --ws websockets \
    --log-level info \
    --access-log /var/log/dataedge/access.log \
    --timeout-keep-alive 300

EnvironmentFile=/opt/dataedge/.env

MemoryMax=1536M
MemoryHigh=1280M

Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=10

TimeoutStartSec=60
TimeoutStopSec=30
WatchdogSec=120

NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/dataedge/backend/data /var/log/dataedge

KillSignal=SIGTERM
KillMode=mixed

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# 6. Reload and enable
echo "▸ Reloading systemd..."
systemctl daemon-reload
systemctl enable dataedge.service

# 7. Clear old crash-loop logs
echo "▸ Clearing old logs..."
> "$LOG_DIR/stdout.log" 2>/dev/null || true
> "$LOG_DIR/stderr.log" 2>/dev/null || true
> "$LOG_DIR/startup_error.log" 2>/dev/null || true

# 8. Start service
echo "▸ Starting Data Edge AI Agent..."
systemctl start dataedge.service
sleep 3

# 9. Check status
echo ""
if systemctl is-active --quiet dataedge.service; then
    echo "  ✅ Data Edge is RUNNING"
    echo "  PID: $(systemctl show dataedge.service --property=MainPID --value)"
    echo "  Logs: journalctl -u dataedge -f"
    echo "  Web:  http://$(hostname -I | awk '{print $1}'):8001/"
else
    echo "  ❌ Data Edge FAILED to start!"
    echo ""
    echo "  Last 20 lines of stderr:"
    tail -20 "$LOG_DIR/stderr.log" 2>/dev/null || echo "  (no stderr output)"
    echo ""
    echo "  Startup error log:"
    cat "$LOG_DIR/startup_error.log" 2>/dev/null || echo "  (no startup error log)"
    echo ""
    echo "  systemctl status dataedge:"
    systemctl status dataedge.service --no-pager 2>&1 | head -20
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Done. Monitor with: journalctl -u dataedge -f"
echo "═══════════════════════════════════════════════════════════════════"
