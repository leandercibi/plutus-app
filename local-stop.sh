#!/bin/bash
# Stop Plutus v2 services running locally.

PROJECT_ROOT="/Users/leander/personal-projects/plutus-app"
cd "$PROJECT_ROOT"

API_PORT=8009
DASH_PORT=8501

echo "=== Stopping Plutus v2 Services ==="
echo ""

_stop_pidfile() {
    local name="$1" file="$2"
    if [ -f "$file" ]; then
        local pid
        pid=$(cat "$file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping $name (PID: $pid)..."
            kill "$pid"
            echo "✓ Stopped"
        else
            echo "⚠️  $name (PID: $pid) not running"
        fi
        rm -f "$file"
    fi
}

_stop_pidfile "plutus-api"       logs/api.pid
_stop_pidfile "plutus-dashboard" logs/dashboard.pid

echo ""
echo "Checking for any remaining processes on ports $API_PORT, $DASH_PORT..."
for port in $API_PORT $DASH_PORT; do
    PID=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "  Killing process on port $port (PID: $PID)"
        kill $PID 2>/dev/null || true
    fi
done

echo ""
echo "✓ All services stopped"
