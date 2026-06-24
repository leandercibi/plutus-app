#!/bin/bash
# Plutus v3 — Docker Compose deploy script
# Run on a fresh Ubuntu 22.04 ARM64 OCI instance (or re-run safely to update).
# Usage: bash deployment/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT/deployment"
ENV_FILE="$DEPLOY_DIR/.env"

green()  { echo -e "\033[0;32m$*\033[0m"; }
yellow() { echo -e "\033[0;33m$*\033[0m"; }
red()    { echo -e "\033[0;31m$*\033[0m"; }
die()    { red "ERROR: $*"; exit 1; }

# ── [1] Docker ─────────────────────────────────────────────────────────────
green "=== [1/5] Docker ==="
if ! command -v docker &>/dev/null; then
  yellow "  Docker not found — installing..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  green "  Docker installed. You may need to log out and back in for group membership."
else
  DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
  green "  Docker $DOCKER_VERSION — OK"
fi

if ! docker compose version &>/dev/null; then
  die "docker compose plugin not found. Install Docker >= 23 which bundles it."
fi
green "  docker compose — OK"

# ── [2] Repo ────────────────────────────────────────────────────────────────
green "=== [2/5] Repository ==="
if [ ! -d "$ROOT/.git" ]; then
  die "Run this script from inside the cloned plutus-app repository."
fi
cd "$ROOT"
green "  Repo root: $ROOT"

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
green "  Branch: $BRANCH  Commit: $COMMIT"

# ── [3] Environment file ───────────────────────────────────────────────────
green "=== [3/5] Environment ==="
if [ ! -f "$ENV_FILE" ]; then
  yellow "  deployment/.env not found — creating from template."
  cp "$DEPLOY_DIR/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  cat << 'MSG'

  ┌─────────────────────────────────────────────────────┐
  │  Edit deployment/.env and set these before retrying: │
  │    API_TOKEN       — long random string              │
  │    POSTGRES_PASSWORD — strong password               │
  │    ANGEL_*         — Angel One SmartAPI creds        │
  │    TELEGRAM_*      — optional Telegram bot           │
  └─────────────────────────────────────────────────────┘
MSG
  yellow "  Re-run this script after filling in the secrets."
  exit 0
fi
chmod 600 "$ENV_FILE"

# Validate required secrets are not placeholder values
for KEY in API_TOKEN POSTGRES_PASSWORD; do
  VAL=$(grep "^${KEY}=" "$ENV_FILE" | cut -d= -f2-)
  if [[ "$VAL" == "change-me"* ]] || [[ -z "$VAL" ]]; then
    die "$KEY in deployment/.env is still a placeholder — set a real value."
  fi
done
green "  deployment/.env OK"

# ── [4] Build & start ──────────────────────────────────────────────────────
green "=== [4/5] Build & start ==="
cd "$DEPLOY_DIR"

green "  Building images (this takes a few minutes on first run)..."
docker compose build

green "  Starting services..."
docker compose up -d

# Wait for API health check (up to 60s)
green "  Waiting for API health check..."
for i in $(seq 1 12); do
  sleep 5
  STATUS=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        s = json.loads(line)
        if s.get('Service') == 'api':
            print(s.get('Health', s.get('State', 'unknown')))
            break
    except Exception:
        pass
" 2>/dev/null || echo "unknown")
  if [[ "$STATUS" == "healthy" ]]; then
    green "  API healthy after $((i * 5))s"
    break
  fi
  if [[ $i -eq 12 ]]; then
    red "  API did not become healthy after 60s"
    docker compose logs api --tail=20
    die "API startup failed — check logs above"
  fi
done

# ── [5] Verify ─────────────────────────────────────────────────────────────
green "=== [5/5] Verify ==="
FRONTEND_PORT=$(grep "^FRONTEND_PORT=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
FRONTEND_PORT="${FRONTEND_PORT:-80}"
BASE_URL="http://localhost:${FRONTEND_PORT}"
API_TOKEN=$(grep "^API_TOKEN=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")

# Healthz
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/healthz" 2>/dev/null || echo "000")
if [[ "$HTTP" == "200" ]]; then
  green "  GET /api/healthz → $HTTP ✓"
else
  red "  GET /api/healthz → $HTTP ✗"
fi

# Auth
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/auth/verify" \
  -H "Authorization: Bearer ${API_TOKEN}" 2>/dev/null || echo "000")
if [[ "$HTTP" == "200" ]]; then
  green "  POST /api/auth/verify → $HTTP ✓"
else
  red "  POST /api/auth/verify → $HTTP ✗ (check API_TOKEN in .env)"
fi

# Frontend SPA
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/" 2>/dev/null || echo "000")
if [[ "$HTTP" == "200" ]]; then
  green "  GET / (React SPA) → $HTTP ✓"
else
  red "  GET / (React SPA) → $HTTP ✗"
fi

SERVER_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
green "=== Done ==="
echo "  App       : http://${SERVER_IP}:${FRONTEND_PORT}"
echo "  API docs  : http://${SERVER_IP}:${FRONTEND_PORT}/api/docs"
echo ""
echo "  Status    : docker compose -f $DEPLOY_DIR/docker-compose.yml ps"
echo "  API logs  : docker compose -f $DEPLOY_DIR/docker-compose.yml logs api -f"
echo "  Scheduler : docker compose -f $DEPLOY_DIR/docker-compose.yml logs scheduler -f"
echo ""
yellow "  If on OCI: open port ${FRONTEND_PORT}/tcp in your Security List."
