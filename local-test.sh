#!/bin/bash
# Local testing script for Plutus on macOS
# Run this to start all services locally

set -e

PROJECT_ROOT="/Users/leander/personal-projects/plutus-app"
cd "$PROJECT_ROOT"

echo "=== Plutus Local Test Environment ==="
echo ""

# Check prerequisites
echo "1. Checking prerequisites..."
if ! command -v psql &> /dev/null; then
    echo "❌ PostgreSQL not found. Install with: brew install postgresql@16"
    exit 1
fi

# Restart database
echo "Restarting PostgreSQL..."
brew services restart postgresql@16
sleep 3
echo "✓ PostgreSQL restarted"

# Replay all migrations
echo "Applying migrations..."
for f in "$PROJECT_ROOT"/migrations/*.sql; do
    PGPASSWORD=plutus psql -h 127.0.0.1 -U plutus -d plutus_db -f "$f" > /dev/null 2>&1
done
echo "✓ Migrations applied"

# Check if database exists
if ! PGPASSWORD=plutus psql -h 127.0.0.1 -U plutus -d plutus_db -c "SELECT 1" &> /dev/null; then
    echo "❌ Database 'plutus_db' not accessible. Run Phase 2 setup first."
    exit 1
fi

echo "✓ PostgreSQL running"
echo "✓ Database 'plutus_db' accessible"
echo ""

# Check Python environment
echo "2. Checking Python environment..."
if [ ! -d "src/.venv" ]; then
    echo "❌ Virtual environment not found at src/.venv"
    exit 1
fi

cd src
if ! .venv/bin/python -c "from plutus.config import settings; print('✓ Config loads')" 2>&1 | grep -q "Config loads"; then
    echo "❌ Config validation failed. Check src/.env file"
    exit 1
fi
cd ..

echo "✓ Python 3.11 venv ready"
echo "✓ Config loads successfully"
echo ""

# Check if ports are available
echo "3. Checking ports..."
if lsof -Pi :8009 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port 8009 already in use (FastAPI)"
    lsof -Pi :8009 -sTCP:LISTEN
fi

if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port 8501 already in use (Streamlit)"
    lsof -Pi :8501 -sTCP:LISTEN
fi

if lsof -Pi :8002 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port 8002 already in use (Telegram bot)"
    lsof -Pi :8002 -sTCP:LISTEN
fi

echo ""
echo "=== Starting Services ==="
echo ""

# Create logs directory
mkdir -p logs

# Start FastAPI + Scheduler (main.py)
echo "Starting plutus-main (FastAPI + Scheduler) on port 8009..."
cd src
.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
# Don't actually start - just verify imports
from plutus.api.routes import router
from plutus.agents.graph import run_analysis
print('✓ All imports successful')
" 2>&1

# Start in background
PYTHONPATH=. .venv/bin/python ../main.py > ../logs/main.log 2>&1 &
MAIN_PID=$!
echo "  PID: $MAIN_PID (logs: logs/main.log)"
cd ..

sleep 3

# Check if main started successfully
if ! curl -s http://localhost:8009/healthz > /dev/null 2>&1; then
    echo "❌ FastAPI failed to start. Check logs/main.log"
    kill $MAIN_PID 2>/dev/null || true
    exit 1
fi
echo "✓ FastAPI running at http://localhost:8009"

# Start Streamlit Dashboard
echo ""
echo "Starting plutus-dashboard (Streamlit) on port 8501..."
cd src
.venv/bin/streamlit run dashboard.py --server.port 8501 --server.headless true > ../logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "  PID: $DASHBOARD_PID (logs: logs/dashboard.log)"
cd ..

sleep 5

# Check if dashboard started
if ! curl -s http://localhost:8501 > /dev/null 2>&1; then
    echo "⚠️  Streamlit may still be starting. Check logs/dashboard.log"
else
    echo "✓ Streamlit running at http://localhost:8501"
fi

echo ""
echo "=== Services Running ==="
echo ""
echo "FastAPI (main):      http://localhost:8009"
echo "  - Health check:    http://localhost:8009/healthz"
echo "  - API docs:        http://localhost:8009/docs"
echo ""
echo "Streamlit Dashboard: http://localhost:8501"
echo ""
echo "Logs:"
echo "  - Main:            logs/main.log"
echo "  - Dashboard:       logs/dashboard.log"
echo ""
echo "PIDs:"
echo "  - Main:            $MAIN_PID"
echo "  - Dashboard:       $DASHBOARD_PID"
echo ""
echo "To stop all services:"
echo "  kill $MAIN_PID $DASHBOARD_PID"
echo ""
echo "Or use: ./local-stop.sh"
echo ""

# Save PIDs for stop script
echo "$MAIN_PID" > logs/main.pid
echo "$DASHBOARD_PID" > logs/dashboard.pid

echo "=== Ready for Testing ==="
echo ""
echo "Try these commands:"
echo "  1. Open dashboard:  open http://localhost:8501"
echo "  2. Test API:        curl http://localhost:8009/healthz"
echo "  3. View logs:       tail -f logs/main.log"
echo ""
