#!/usr/bin/env bash
# start_server.sh — Start Pond API on port 3209 in the background
set -euo pipefail

APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"
LOG_FILE="$APP_DIR/uvicorn.log"
PORT=3000

cd "$APP_DIR"

# Stop any existing processes on 3000 and 3209
"$APP_DIR/stop_server.sh" 2>/dev/null || true

echo "Starting Pond API endlessly on port $PORT..."
(nohup "$APP_DIR/runner.sh" </dev/null >/dev/null 2>&1 & echo $! > "$PID_FILE")

sleep 3
if fuser ${PORT}/tcp >/dev/null 2>&1 || ss -tulpn | grep -q ":${PORT} "; then
    echo "Server is running endlessly on port $PORT"
    echo "Logs available at: $LOG_FILE"
else
    echo "Server status: checking..."
    tail -n 10 "$LOG_FILE"
fi
