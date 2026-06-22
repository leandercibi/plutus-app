#!/bin/bash
set -e
export PAGER=cat

# Plutus v2 Deployment Script for Ubuntu 22.04 (ARM64)
# Greenfield v2 layout: repo-root .venv + .env, pyproject.toml, src/plutus package.
# Services: plutus-api (uvicorn), plutus-scheduler (APScheduler), plutus-dashboard (Streamlit).

ROOT=/home/ubuntu/plutus-app

echo "=== Step 1: System packages ==="
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  python3.11 python3.11-venv python3.11-dev \
  build-essential libssl-dev libffi-dev libpq-dev \
  postgresql-16 postgresql-contrib-16 \
  git curl wget unzip

# cloudflared (ARM64 .deb)
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

python3.11 --version

echo "=== Step 2: PostgreSQL ==="
sudo systemctl enable postgresql
sudo systemctl start postgresql

sudo -u postgres psql <<'EOF'
CREATE USER plutus WITH PASSWORD 'plutus';
CREATE DATABASE plutus_db OWNER plutus;
GRANT ALL PRIVILEGES ON DATABASE plutus_db TO plutus;
\q
EOF

PGPASSWORD=plutus psql -U plutus -d plutus_db -h 127.0.0.1 --no-psqlrc -t -c "SELECT version();"

echo "=== Step 3: Project ==="
echo "Assumes the repo is at $ROOT (git clone or rsync from your Mac)."
echo "  rsync -avz /Users/leander/personal-projects/plutus-app/ ubuntu@<OCI_IP>:$ROOT/"

echo "=== Step 4: Python environment (repo-root venv, pyproject) ==="
cd "$ROOT"
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
# Runtime install from pyproject (add [dev] to also run the test suite on the box).
pip install -e .

# Verify key v2 packages (all pure-Python or ARM64 wheels).
python -c "import fastapi, uvicorn; print('fastapi/uvicorn OK')"
python -c "import streamlit; print('streamlit OK')"
python -c "import apscheduler; print('apscheduler OK')"
python -c "import sqlalchemy, pydantic, pandas, numpy, scipy; print('core OK')"

echo "=== Step 5: Environment file (repo root .env) ==="
echo "Create $ROOT/.env from .env.example and fill secrets/DB_URL."
echo "  cp $ROOT/.env.example $ROOT/.env && nano $ROOT/.env"
echo "Prod requires: ENVIRONMENT=prod, a non-sqlite DB_URL, FRESHNESS_ASSERT_ENABLED=true."
read -p "Press Enter after you've created and secured (.env -> chmod 600) the .env file..."
chmod 600 "$ROOT/.env" || true

echo "=== Step 6: Initialize database ==="
cd "$ROOT"
source .venv/bin/activate
python -m plutus.db.init_db
echo "Schema created."

echo "=== Step 7: Smoke test (v2 entry points) ==="
# API app imports and exposes /healthz.
python -c "from plutus.api.main import app; print('FastAPI app OK')"
# Scheduler wires its jobs.
python -c "
from plutus.config.settings import get_settings
from plutus.scheduler.runner import build_scheduler
s = build_scheduler(get_settings())
print('scheduler jobs:', sorted(j.id for j in s.get_jobs()))
"
# Dashboard entry point exists.
test -f src/plutus/dashboard/app.py && echo "dashboard entry OK"

echo ""
echo "=== Deployment prepared ==="
echo "Next: install systemd units (Step 8 in deployment/README.md):"
echo "  sudo cp deployment/plutus-api.service       /etc/systemd/system/"
echo "  sudo cp deployment/plutus-scheduler.service /etc/systemd/system/"
echo "  sudo cp deployment/plutus-dashboard.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now plutus-api plutus-scheduler plutus-dashboard"
