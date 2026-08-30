#!/usr/bin/env bash
# stop_server.sh — Stop Pond API
set -euo pipefail

APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"
PORT=3000

# Kill runner supervisor and uvicorn processes
pkill -f "$APP_DIR/runner.sh" 2>/dev/null || true
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
fuser -k 3209/tcp 2>/dev/null || true

rm -f "$PID_FILE"
echo "Pond API stopped."
