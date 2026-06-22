#!/bin/bash
# Plutus v2 — server setup & start script
# Run once (or re-run safely) on a fresh Ubuntu 22.04 ARM64 OCI instance.
# Usage: bash deployment/deploy.sh
set -euo pipefail

ROOT=/home/ubuntu/plutus-app
VENV="$ROOT/.venv"
ENV_FILE="$ROOT/.env"

green()  { echo -e "\033[0;32m$*\033[0m"; }
yellow() { echo -e "\033[0;33m$*\033[0m"; }
red()    { echo -e "\033[0;31m$*\033[0m"; }
die()    { red "ERROR: $*"; exit 1; }

green "=== [1/7] System packages ==="
sudo apt-get update -q
sudo apt-get install -y -q \
  python3 python3-venv python3-dev \
  build-essential libssl-dev libffi-dev libpq-dev \
  postgresql postgresql-contrib \
  git curl

green "=== [2/7] PostgreSQL ==="
sudo systemctl enable postgresql --quiet
sudo systemctl start postgresql

# Create user + db only if they don't exist yet
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='plutus'" \
  | grep -q 1 || sudo -u postgres psql -c "CREATE USER plutus WITH PASSWORD 'plutus';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='plutus_db'" \
  | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE plutus_db OWNER plutus;"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE plutus_db TO plutus;" -q
sudo -u postgres psql -c "ALTER USER plutus WITH SUPERUSER;" -q

PGPASSWORD=plutus psql -U plutus -d plutus_db -h 127.0.0.1 -c "SELECT version();" -q \
  && green "  PostgreSQL OK" || die "Cannot connect to plutus_db"

green "=== [3/7] Python virtualenv ==="
cd "$ROOT"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
  green "  Created .venv"
fi
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r src/requirements.txt -q
green "  Dependencies installed"

green "=== [4/7] Environment file ==="
if [ ! -f "$ENV_FILE" ]; then
  yellow "  .env not found. Creating a template — fill in the secrets before continuing."
  cat > "$ENV_FILE" << 'ENVEOF'
ENVIRONMENT=prod
DB_URL=postgresql+psycopg://plutus:plutus@127.0.0.1:5432/plutus_db

# Angel One SmartAPI
ANGEL_API_KEY=
ANGEL_CLIENT_ID=
ANGEL_PASSWORD=
ANGEL_TOTP_SECRET=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Optional
FRESHNESS_ASSERT_ENABLED=true
ENVEOF
  chmod 600 "$ENV_FILE"
  yellow "  Edit $ENV_FILE and re-run this script."
  exit 0
fi
chmod 600 "$ENV_FILE"
green "  .env found"

green "=== [5/7] Database schema ==="
cd "$ROOT"
"$VENV/bin/python" -m plutus.db.init_db && green "  Schema OK"

green "=== [6/7] Systemd services ==="
for svc in plutus-api plutus-scheduler plutus-dashboard; do
  sudo cp "$ROOT/deployment/${svc}.service" /etc/systemd/system/
done
sudo systemctl daemon-reload

for svc in plutus-api plutus-scheduler plutus-dashboard; do
  sudo systemctl enable "$svc" --quiet
  sudo systemctl restart "$svc"
  sleep 2
  STATUS=$(sudo systemctl is-active "$svc" 2>&1)
  if [ "$STATUS" = "active" ]; then
    green "  $svc — active"
  else
    red "  $svc — $STATUS  (check: sudo journalctl -u $svc -n 30)"
  fi
done

green "=== [7/7] Firewall ==="
if command -v ufw &>/dev/null && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 8009/tcp -q && green "  Port 8009 (API) allowed"
  sudo ufw allow 8501/tcp -q && green "  Port 8501 (Dashboard) allowed"
else
  yellow "  ufw not active — skip (configure OCI Security List manually)"
fi

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || echo "<server-ip>")
echo ""
green "=== Done ==="
echo "  Dashboard : http://${SERVER_IP}:8501"
echo "  API docs  : http://${SERVER_IP}:8009/docs"
echo ""
echo "  Logs      : sudo journalctl -u plutus-api -f"
echo "              sudo journalctl -u plutus-dashboard -f"
echo "              sudo journalctl -u plutus-scheduler -f"
echo ""
yellow "  Reminder: open ports 8009 + 8501 in your OCI Security List if not done yet."
