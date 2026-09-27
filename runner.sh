#!/usr/bin/env bash
# runner.sh — Endless supervisor loop for Backend (3000), Frontend (4000), and Port Bridge (3209, 4209)
APP_DIR="/home/student/pond_panning"
LOG_FILE="$APP_DIR/supervisor.log"

cd "$APP_DIR"

while true; do
    # 1. Ensure Backend is running on port 3000
    if ! ss -tulpn | grep -q ":3000 "; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Backend API on port 3000..." >> "$LOG_FILE"
        nohup "$APP_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 3000 --workers 1 >> "$APP_DIR/backend_3000.log" 2>&1 &
    fi

    # 2. Ensure Frontend is running on port 4000
    if ! ss -tulpn | grep -q ":4000 "; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Frontend UI on port 4000..." >> "$LOG_FILE"
        nohup "$APP_DIR/.venv/bin/python3" "$APP_DIR/frontend_server.py" >> "$APP_DIR/frontend_4000.log" 2>&1 &
    fi

    # 3. Ensure Port Bridge (3209->3000, 4209->4000) is running
    if ! ss -tulpn | grep -q ":3209 " || ! ss -tulpn | grep -q ":4209 "; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Port Bridge (3209->3000, 4209->4000)..." >> "$LOG_FILE"
        nohup "$APP_DIR/.venv/bin/python3" "$APP_DIR/port_bridge.py" >> "$APP_DIR/port_bridge.log" 2>&1 &
    fi

    sleep 5
done

