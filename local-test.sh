#!/bin/bash
# Local testing script for Plutus v2 on macOS — starts API + dashboard locally.
set -e

PROJECT_ROOT="/Users/leander/personal-projects/plutus-app"
cd "$PROJECT_ROOT"

API_PORT=8009
DASH_PORT=8501

echo "=== Plutus v2 Local Test Environment ==="
echo ""

# 1. Python environment (repo-root venv)
echo "1. Checking Python environment..."
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found at .venv"
    echo "   Create it: python3.11 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

if ! .venv/bin/python -c "from plutus.config.settings import get_settings; get_settings()" 2>&1; then
    echo "❌ Settings failed to load. Check your .env (or run with dev defaults)."
    exit 1
fi
echo "✓ venv ready, settings load"
echo ""

# Dev uses sqlite by default (Settings.db_url) — no Postgres required locally.
echo "2. Initializing database (sqlite dev default unless DB_URL overrides)..."
.venv/bin/python -m plutus.db.init_db && echo "✓ schema ready"
echo ""

# 3. Port checks
echo "3. Checking ports..."
for port in $API_PORT $DASH_PORT; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "⚠️  Port $port already in use"
        lsof -Pi :$port -sTCP:LISTEN
    fi
done
echo ""

echo "=== Starting Services ==="
mkdir -p logs

# Smoke-check imports before launching.
.venv/bin/python -c "from plutus.api.main import app; print('✓ FastAPI app imports')"

# FastAPI (uvicorn)
echo "Starting plutus-api (uvicorn) on port $API_PORT..."
.venv/bin/uvicorn plutus.api.main:app --host 127.0.0.1 --port $API_PORT > logs/api.log 2>&1 &
API_PID=$!
echo "  PID: $API_PID (logs: logs/api.log)"
sleep 3

if ! curl -s "http://localhost:$API_PORT/healthz" > /dev/null 2>&1; then
    echo "❌ FastAPI failed to start. Check logs/api.log"
    kill $API_PID 2>/dev/null || true
    exit 1
fi
echo "✓ FastAPI running at http://localhost:$API_PORT"

# Streamlit dashboard
echo ""
echo "Starting plutus-dashboard (Streamlit) on port $DASH_PORT..."
.venv/bin/streamlit run src/plutus/dashboard/app.py \
    --server.port $DASH_PORT --server.headless true > logs/dashboard.log 2>&1 &
DASH_PID=$!
echo "  PID: $DASH_PID (logs: logs/dashboard.log)"
sleep 5

if ! curl -s "http://localhost:$DASH_PORT" > /dev/null 2>&1; then
    echo "⚠️  Streamlit may still be starting. Check logs/dashboard.log"
else
    echo "✓ Streamlit running at http://localhost:$DASH_PORT"
fi

echo ""
echo "=== Services Running ==="
echo "FastAPI:    http://localhost:$API_PORT   (/healthz, /docs)"
echo "Dashboard:  http://localhost:$DASH_PORT"
echo ""
echo "Logs: logs/api.log, logs/dashboard.log"
echo "PIDs: api=$API_PID dashboard=$DASH_PID"
echo "Stop: ./local-stop.sh"

echo "$API_PID"  > logs/api.pid
echo "$DASH_PID" > logs/dashboard.pid

echo ""
echo "=== Ready ==="
echo "  open http://localhost:$DASH_PORT"
echo "  curl http://localhost:$API_PORT/healthz"
echo "  tail -f logs/api.log"
