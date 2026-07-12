#!/bin/bash
# =============================================================================
# Agentic Trading Desk — Server03 Setup Script
# IBKR Client Portal Gateway + REST Web API (no Docker, no password on disk)
# =============================================================================
#
# Usage:
#   cd /home/liron/.openclaw/agentic-trading-desk-workspace
#   bash setup_server03.sh
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Agentic Trading Desk — Server03 Setup                  ║"
echo "║  IBKR Client Portal Gateway + REST Web API              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

GATEWAY_DIR="${HOME}/ibkr-gateway"

# ── Step 1: System dependencies ──
echo "▶ [1/5] Checking system dependencies..."
if java -version 2>&1 | grep -q "openjdk version"; then
  echo "  ✅ Java already installed"
  java -version 2>&1 | head -1
else
  echo "  Installing Java..."
  sudo apt update -qq
  sudo apt install -y openjdk-21-jre-headless
fi

if ! command -v curl &>/dev/null; then
  sudo apt install -y curl
fi

echo ""

# ── Step 2: Download Gateway ──
echo "▶ [2/5] Downloading Client Portal Gateway..."
if [ -f "${GATEWAY_DIR}/dist/ibgroup.web.core.iblink.router.clientportal.gw.jar" ]; then
  echo "  ✅ Already downloaded at ${GATEWAY_DIR}"
else
  mkdir -p "${GATEWAY_DIR}"
  cd /tmp
  echo "  Downloading (~10MB)..."
  curl -sLO "https://download2.interactivebrokers.com/portal/clientportal.gw.zip"
  echo "  Extracting..."
  unzip -q clientportal.gw.zip -d "${GATEWAY_DIR}"
  rm clientportal.gw.zip
  echo "  ✅ Extracted to ${GATEWAY_DIR}"
fi

echo ""

# ── Step 3: Write config (for reference only — --conf flag is broken in this gateway version) ──
echo "▶ [3/5] Config note..."
echo "  ℹ️  Gateway uses built-in defaults (port 5000). The --conf flag is broken in this gateway build."
echo "  ℹ️  Market data subscriptions needed in IBKR account for live quotes."
echo "  ✅ Historical data and positions work without market data subscriptions."

echo ""

# ── Step 4: Create systemd service (no --conf flag) ──
echo "▶ [4/5] Creating systemd service for auto-start..."
SERVICE_FILE="/etc/systemd/system/ibkr-gateway.service"
sudo tee "${SERVICE_FILE}" > /dev/null << UNITEOF
[Unit]
Description=IBKR Client Portal Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${GATEWAY_DIR}
ExecStart=/usr/bin/java -server \
    -Dvertx.disableDnsResolver=true \
    -Djava.net.preferIPv4Stack=true \
    -Dvertx.logger-delegate-factory-class-name=io.vertx.core.logging.SLF4JLogDelegateFactory \
    -Dnologback.statusListenerClass=ch.qos.logback.core.status.OnConsoleStatusListener \
    -Dnolog4j.debug=true \
    -Dnolog4j2.debug=true \
    -cp "root:dist/ibgroup.web.core.iblink.router.clientportal.gw.jar:build/lib/runtime/*" \
    ibgroup.web.core.clientportal.gw.GatewayStart
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNITEOF
echo "  ✅ Service file created (no --conf flag)"

echo ""

# ── Step 5: Start gateway ──
echo "▶ [5/5] Starting IBKR Gateway..."
sudo systemctl daemon-reload
sudo systemctl enable ibkr-gateway
sudo systemctl restart ibkr-gateway

echo ""
echo "  ⏳  Waiting for gateway to initialize..."
for i in $(seq 1 30); do
  if ss -tlnp | grep -q ':5000'; then
    echo "  ✅ Gateway ready on port 5000"
    break
  fi
  echo "  ...waiting ($i/30)"
  sleep 2
done

echo ""
echo "── Gateway diagnostics ──"
echo ""

# Test 1: Port listening
echo "  [1/4] Port check..."
if ss -tlnp | grep -q ':5000'; then
  echo "  ✅ Port 5000 is listening"
else
  echo "  ❌ Port 5000 NOT listening"
  echo "     Check: journalctl -u ibkr-gateway --no-pager -n 20"
fi

# Test 2: Process alive
echo "  [2/4] Process check..."
if pgrep -f "clientportal.gw" > /dev/null 2>&1; then
  PID=$(pgrep -f "clientportal.gw")
  echo "  ✅ Gateway process running (PID: ${PID})"
else
  echo "  ❌ Gateway process NOT running"
fi

# Test 3: HTTPS responds
echo "  [3/4] HTTPS endpoint check..."
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" "https://localhost:5000/" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "000" ]; then
  echo "  ✅ HTTPS responding (HTTP ${HTTP_CODE})"
else
  echo "  ❌ HTTPS not responding"
  echo "     Check: journalctl -u ibkr-gateway --no-pager -n 20"
fi

# Test 4: Python helper
echo "  [4/4] Python helper check..."
if python3 -c "import json, ssl, urllib.request; print('  ✅ Python stdlib ready')" 2>/dev/null; then
  echo "  📋 Helper: scripts/ibkr_webapi.py"
else
  echo "  ⚠  Python check failed"
fi

echo ""
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "  Gateway: https://localhost:5000"
echo "  Auto-restart: systemd (enabled)"
echo "  Logs: journalctl -u ibkr-gateway -f"
echo ""
echo "  ─── ONE-TIME AUTH (already done) ───"
echo ""
echo "  From your local machine:"
echo "    ssh -L 5000:localhost:5000 liron@server03"
echo "    open https://localhost:5000 in browser, log in"
echo ""
echo "  ─── TESTING ───"
echo ""
echo "  cd ${SCRIPT_DIR}"
echo "  python3 scripts/ibkr_webapi.py auth-check"
echo "  python3 scripts/ibkr_webapi.py historicals AAPL"
echo "  python3 scripts/ibkr_webapi.py positions"
echo "  python3 scripts/ibkr_webapi.py portfolio"
echo ""
echo "  ─── FULL PIPELINE ───"
echo ""
echo "  python3 scripts/ibkr_webapi.py historicals AAPL > /tmp/ticker.json"
echo "  python3 -c \"import json; d=json.load(open('/tmp/ticker.json')); json.dump({'symbol':'AAPL','close':d['close'],'macro_score':0,'holding':false}, open('/tmp/score.json','w'))\""
echo "  python3 scripts/score.py /tmp/score.json"
echo ""
echo "  ─── MANAGE ───"
echo ""
echo "  View logs:   journalctl -u ibkr-gateway -f"
echo "  Restart:     sudo systemctl restart ibkr-gateway"
echo "  Stop:        sudo systemctl stop ibkr-gateway"
echo ""
echo "══════════════════════════════════════════════════════════════"
