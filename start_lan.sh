#!/bin/bash
# NEWVISION LAN Launcher
# Explicitly binds FastAPI/Uvicorn to 0.0.0.0:8000 for local network access (Kali / ESP32 AP)
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

export NEWVISION_HOST="0.0.0.0"
export NEWVISION_HTTP_PORT="8000"
export NEWVISION_UDP_PORT="5005"

echo "=================================================="
echo "  Starting NEWVISION Backend on LAN (0.0.0.0:8000)"
echo "  UDP Telemetry Port: 5005"
echo "  Dashboard: http://192.168.4.100:8000/dashboard/newview.html"
echo "=================================================="

exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
