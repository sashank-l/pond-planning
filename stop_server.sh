#!/usr/bin/env bash
# stop_server.sh — Stop Pond API
set -euo pipefail

APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"
PORT=3209

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping Pond API (PID $PID)..."
        kill "$PID" || true
        sleep 1
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi

fuser -k ${PORT}/tcp 2>/dev/null || true
echo "Pond API stopped."
