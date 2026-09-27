#!/usr/bin/env bash
# start_server.sh — Start Backend (3000/3209) and Frontend (4000/4209)
set -euo pipefail

APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"
LOG_FILE="$APP_DIR/supervisor.log"

cd "$APP_DIR"

# Stop any existing processes
"$APP_DIR/stop_server.sh" 2>/dev/null || true

echo "Starting Endless Supervisor for Pond Planning System..."
(nohup "$APP_DIR/runner.sh" </dev/null >/dev/null 2>&1 & echo $! > "$PID_FILE")

sleep 4

echo "=== Port Status ==="
ss -tulpn | grep -E '3000|3209|4000|4209' || true
echo "Supervisor is running in background (PID: $(cat "$PID_FILE" 2>/dev/null || echo '?'))"
echo "Logs available at: $LOG_FILE"

