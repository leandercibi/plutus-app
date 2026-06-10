#!/bin/bash
# Stop all Plutus services running locally

PROJECT_ROOT="/Users/leander/personal-projects/plutus-app"
cd "$PROJECT_ROOT"

echo "=== Stopping Plutus Services ==="
echo ""

# Read PIDs from files
if [ -f "logs/main.pid" ]; then
    MAIN_PID=$(cat logs/main.pid)
    if kill -0 $MAIN_PID 2>/dev/null; then
        echo "Stopping plutus-main (PID: $MAIN_PID)..."
        kill $MAIN_PID
        echo "✓ Stopped"
    else
        echo "⚠️  plutus-main (PID: $MAIN_PID) not running"
    fi
    rm logs/main.pid
fi

if [ -f "logs/dashboard.pid" ]; then
    DASHBOARD_PID=$(cat logs/dashboard.pid)
    if kill -0 $DASHBOARD_PID 2>/dev/null; then
        echo "Stopping plutus-dashboard (PID: $DASHBOARD_PID)..."
        kill $DASHBOARD_PID
        echo "✓ Stopped"
    else
        echo "⚠️  plutus-dashboard (PID: $DASHBOARD_PID) not running"
    fi
    rm logs/dashboard.pid
fi

# Fallback: kill by port
echo ""
echo "Checking for any remaining processes on ports 8009, 8501..."

for port in 8009 8501; do
    PID=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$PID" ]; then
        echo "  Killing process on port $port (PID: $PID)"
        kill $PID 2>/dev/null || true
    fi
done

echo ""
echo "✓ All services stopped"

# Restart database
echo "Restarting PostgreSQL..."
brew services restart postgresql@16
echo "✓ PostgreSQL restarted"
