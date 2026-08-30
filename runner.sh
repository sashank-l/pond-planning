#!/usr/bin/env bash
# runner.sh — Endless supervisor loop for Pond API on port 3000
APP_DIR="/home/student/pond_panning"
LOG_FILE="$APP_DIR/uvicorn.log"
PORT=3000

cd "$APP_DIR"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Pond API on port $PORT..." >> "$LOG_FILE"
    "$APP_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Server exited with code $EXIT_CODE. Restarting in 2s..." >> "$LOG_FILE"
    sleep 2
done
