#!/usr/bin/env bash
# stop_server.sh — Stop all Pond Planning and Telemetry services
APP_DIR="/home/student/pond_panning"
PID_FILE="$APP_DIR/app.pid"

# Kill supervisor loop
pkill -f "$APP_DIR/runner.sh" 2>/dev/null || true
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
pkill -f 'frontend_server.py' 2>/dev/null || true
pkill -f 'telemetry_server.py' 2>/dev/null || true
pkill -f 'jaeger-all-in-one' 2>/dev/null || true
pkill -f 'port_bridge.py' 2>/dev/null || true

# Free ports
fuser -k 3000/tcp 2>/dev/null || true
fuser -k 3209/tcp 2>/dev/null || true
fuser -k 4000/tcp 2>/dev/null || true
fuser -k 4209/tcp 2>/dev/null || true
fuser -k 5200/tcp 2>/dev/null || true
fuser -k 5209/tcp 2>/dev/null || true
fuser -k 16686/tcp 2>/dev/null || true
fuser -k 6209/tcp 2>/dev/null || true
fuser -k 4318/tcp 2>/dev/null || true
fuser -k 7209/tcp 2>/dev/null || true

rm -f "$PID_FILE"
echo "All Pond Planning and OpenTelemetry services stopped."
