#!/usr/bin/env bash
# start_server.sh — Start Pond API on port 3209 in the background
set -euo pipefail

APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"
LOG_FILE="$APP_DIR/uvicorn.log"
PORT=3209

cd "$APP_DIR"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Server is already running with PID $PID"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Kill any existing process on port 3209 just in case
fuser -k ${PORT}/tcp 2>/dev/null || true

echo "Starting Pond API on port $PORT..."
nohup "$APP_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

sleep 2
if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "Server started successfully with PID $(cat "$PID_FILE")"
    echo "Logs at: $LOG_FILE"
else
    echo "Server failed to start. Last log lines:"
    cat "$LOG_FILE"
    exit 1
fi
