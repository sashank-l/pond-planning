#!/usr/bin/env bash
# runner.sh — Endless supervisor loop for Backend, Frontend, OpenTelemetry Dashboard, Jaeger, and Port Bridge
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

    # 3. Ensure OpenTelemetry Dashboard is running on port 5200
    if ! ss -tulpn | grep -q ":5200 "; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting OpenTelemetry Dashboard on port 5200..." >> "$LOG_FILE"
        nohup "$APP_DIR/.venv/bin/python3" "$APP_DIR/telemetry_server.py" >> "$APP_DIR/telemetry_5200.log" 2>&1 &
    fi

    # 4. Ensure Jaeger All-in-One is running (if binary present)
    if [ -f "$APP_DIR/jaeger-all-in-one" ] && ! ss -tulpn | grep -q ":16686 "; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Jaeger All-in-One on port 16686..." >> "$LOG_FILE"
        nohup "$APP_DIR/jaeger-all-in-one" >> "$APP_DIR/jaeger.log" 2>&1 &
    fi

    # 5. Ensure Multi-Port Bridge is running (3209->3000, 4209->4000, 5209->5200, 6209->16686, 7209->4318)
    if ! ss -tulpn | grep -q ":3209 " || ! ss -tulpn | grep -q ":5209 "; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Multi-Port Bridge..." >> "$LOG_FILE"
        nohup "$APP_DIR/.venv/bin/python3" "$APP_DIR/port_bridge.py" >> "$APP_DIR/port_bridge.log" 2>&1 &
    fi

    sleep 5
done
