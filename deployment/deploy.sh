#!/bin/bash
set -e
export PAGER=cat
export PGPASSWORD=plutus

# Plutus Deployment Script for Ubuntu 22.04 (ARM64)
# Consolidates Steps 1-7 from 15_deployment.md

echo "=== Step 1: Initial OCI Instance Setup ==="

# Update system
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y \
  python3.11 python3.11-venv python3.11-dev \
  build-essential libssl-dev libffi-dev libpq-dev \
  postgresql-16 postgresql-contrib-16 \
  git curl wget unzip

# cloudflared (ARM64 .deb)
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

# Verify Python version
python3.11 --version

echo "=== Step 2: PostgreSQL Setup ==="

# Start PostgreSQL
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql <<'EOF'
CREATE USER plutus WITH PASSWORD 'plutus';
CREATE DATABASE plutus_db OWNER plutus;
GRANT ALL PRIVILEGES ON DATABASE plutus_db TO plutus;
\q
EOF

# Test connection
PGPASSWORD=plutus psql -U plutus -d plutus_db -h 127.0.0.1 --no-psqlrc -t -c "SELECT version();"

echo "=== Step 3: Clone / Upload Project ==="
echo "Note: This script assumes project is already at /home/ubuntu/plutus-app/"
echo "If not, run: git clone https://github.com/yourusername/plutus-app.git /home/ubuntu/plutus-app"
echo "Or use rsync from your Mac: rsync -avz /Users/leander/personal-projects/plutus-app/ ubuntu@<OCI_IP>:/home/ubuntu/plutus-app/"

echo "=== Step 4: Python Environment ==="

cd /home/ubuntu/plutus-app/src

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify key packages (ARM64 compatibility check)
python -c "import backtrader; print('backtrader OK')"
python -c "import pandas_ta; print('pandas_ta OK')"
python -c "import langgraph; print('langgraph OK')"
python -c "import telegram; print('python-telegram-bot OK')"
python -c "import apscheduler; print('apscheduler OK')"
python -c "import fastapi, uvicorn; print('fastapi/uvicorn OK')"

echo "=== Step 5: Environment Variables ==="
echo "Please create /home/ubuntu/plutus-app/src/.env from the template in 03_config_env.md"
echo "After creating, run: chmod 600 /home/ubuntu/plutus-app/src/.env"
read -p "Press Enter after you've created the .env file..."

echo "=== Step 6: Initialize Database ==="

cd /home/ubuntu/plutus-app/src
source .venv/bin/activate

python -m plutus.db.init_db

echo "=== Step 7: Test Run ==="
echo "Testing agent pipeline..."

python -c "
from plutus.agents.graph import run_analysis
r = run_analysis('RELIANCE', 'NSE', use_cache=False)
print(r['recommendation'], r.get('confidence'))
"

echo ""
echo "=== Deployment Complete ==="
echo "Next steps:"
echo "1. Set up systemd services (see deployment/README.md Step 8)"
echo "2. Configure OCI firewall (see deployment/README.md Step 9)"
echo "3. Set up Cloudflare Tunnel (see deployment/README.md Step 10)"
