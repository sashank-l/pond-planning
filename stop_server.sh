#!/usr/bin/env bash
# stop_server.sh — Stop all Pond Planning services
APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"

# Kill supervisor loop
pkill -f "$APP_DIR/runner.sh" 2>/dev/null || true
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
pkill -f 'frontend_server.py' 2>/dev/null || true
pkill -f 'port_bridge.py' 2>/dev/null || true

# Free ports
fuser -k 3000/tcp 2>/dev/null || true
fuser -k 3209/tcp 2>/dev/null || true
fuser -k 4000/tcp 2>/dev/null || true
fuser -k 4209/tcp 2>/dev/null || true

rm -f "$PID_FILE"
echo "All Pond Planning services stopped."

