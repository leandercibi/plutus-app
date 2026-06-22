# Plutus v2 Deployment Guide

> **Service split.** Plutus v2 runs as **three** application services plus PostgreSQL on a single OCI A1.flex VM.
> - `plutus-api.service` — FastAPI via uvicorn on `:8000` — `uvicorn plutus.api.main:app`
> - `plutus-scheduler.service` — APScheduler (Sunday full, Monday re-val, daily exit, freshness, weekly postmortem; midweek mini gated) — `python -m plutus.scheduler.runner`
> - `plutus-dashboard.service` — Streamlit on `:8501` — `streamlit run src/plutus/dashboard/app.py`
> - `postgresql.service` (system)
>
> v2 layout note: the virtualenv and `.env` live at the **repo root** (`/home/ubuntu/plutus-app/.venv`, `/home/ubuntu/plutus-app/.env`). Python lives under `src/plutus/`. Dependencies are installed from `pyproject.toml` (`pip install -e .`), not a `requirements.txt`. There is no standalone Telegram bot process in v2 — alerts are push-only via `plutus.alerts` invoked from the scheduler.

---

## Instance Specs

- **Shape:** VM.Standard.A1.Flex
- **OCPUs:** 2
- **RAM:** 12 GB
- **OS:** Ubuntu 22.04 LTS (ARM64 / aarch64)
- **Storage:** 50 GB boot volume (minimum)

---

## Quick Start

1. SSH into your OCI instance: `ssh ubuntu@<OCI_PUBLIC_IP>`
2. Upload this project to `/home/ubuntu/plutus-app/`
3. Run the deployment script: `bash /home/ubuntu/plutus-app/deployment/deploy.sh`
4. Follow Steps 8-10 below to set up services and public access

---

## Step 1: Initial OCI Instance Setup

```bash
ssh ubuntu@<OCI_PUBLIC_IP>
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  python3.11 python3.11-venv python3.11-dev \
  build-essential libssl-dev libffi-dev libpq-dev \
  postgresql-16 postgresql-contrib-16 \
  git curl wget unzip

# cloudflared (ARM64 .deb)
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared-linux-arm64.deb

python3.11 --version   # 3.11.x
```

---

## Step 2: PostgreSQL Setup

```bash
sudo systemctl enable postgresql
sudo systemctl start postgresql

sudo -u postgres psql <<'EOF'
CREATE USER plutus WITH PASSWORD 'plutus';
CREATE DATABASE plutus_db OWNER plutus;
GRANT ALL PRIVILEGES ON DATABASE plutus_db TO plutus;
\q
EOF

psql -U plutus -d plutus_db -h 127.0.0.1 -c "SELECT version();"
```

Prod uses the Postgres URL via `DB_URL` in `.env` (e.g. `postgresql+psycopg://plutus:plutus@127.0.0.1/plutus_db`). The `Settings` class rejects a sqlite URL when `ENVIRONMENT=prod`.

---

## Step 3: Clone / Upload Project

```bash
# Option A: Git
git clone https://github.com/yourusername/plutus-app.git /home/ubuntu/plutus-app

# Option B: rsync from your Mac
rsync -avz /Users/leander/personal-projects/plutus-app/ \
    ubuntu@<OCI_IP>:/home/ubuntu/plutus-app/
```

The deployed tree is rooted at `/home/ubuntu/plutus-app/`. Python lives under `src/plutus/`; the venv and `.env` sit at the repo root.

---

## Step 4: Python Environment (repo-root venv + pyproject)

```bash
cd /home/ubuntu/plutus-app
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .            # runtime deps from pyproject.toml
# To also run the test suite on the box: pip install -e ".[dev]"

# Verify key v2 packages (all pure-Python or have ARM64 wheels)
python -c "import fastapi, uvicorn; print('fastapi/uvicorn OK')"
python -c "import streamlit; print('streamlit OK')"
python -c "import apscheduler; print('apscheduler OK')"
python -c "import sqlalchemy, pydantic, pandas, numpy, scipy; print('core OK')"
```

---

## Step 5: Environment Variables (repo-root `.env`)

```bash
cd /home/ubuntu/plutus-app
cp .env.example .env
nano .env          # set ENVIRONMENT=prod, DB_URL=postgresql+psycopg://..., secrets
chmod 600 .env
```

Prod-only validation enforced at `Settings` construction:
- `DB_URL` must not be sqlite.
- `FRESHNESS_ASSERT_ENABLED=true` (B11 must be on in prod).
- `RISK_PER_TRADE_PCT <= 0.02`.

---

## Step 6: Initialize Database

```bash
cd /home/ubuntu/plutus-app
source .venv/bin/activate
python -m plutus.db.init_db
```

> Alembic baseline migration is the long-term path; `init_db` (`create_all`) is the current bootstrap.

---

## Step 7: Test Run (Before Setting Up Services)

```bash
cd /home/ubuntu/plutus-app
source .venv/bin/activate

# API (Ctrl-C after a few seconds)
uvicorn plutus.api.main:app --host 0.0.0.0 --port 8000
# then in another shell: curl http://localhost:8000/healthz

# Scheduler — prints the registered job ids and starts (Ctrl-C to stop)
python -m plutus.scheduler.runner

# Dashboard
streamlit run src/plutus/dashboard/app.py --server.port 8501 --server.address 0.0.0.0
```

---

## Step 8: Systemd Services

### IST scheduling note

The scheduler is built with `timezone="Asia/Kolkata"` and every `CronTrigger` carries the same tz (see `plutus/scheduler/triggers.py` and `runner.py`). The host clock stays UTC (OCI default); we deliberately **do not** set `Environment=TZ=...` in the unit files — one source of truth, in code.

### Install Service Files

```bash
sudo cp /home/ubuntu/plutus-app/deployment/plutus-api.service       /etc/systemd/system/
sudo cp /home/ubuntu/plutus-app/deployment/plutus-scheduler.service /etc/systemd/system/
sudo cp /home/ubuntu/plutus-app/deployment/plutus-dashboard.service /etc/systemd/system/
```

### Enable and Start All Three

```bash
sudo systemctl daemon-reload
sudo systemctl enable  plutus-api plutus-scheduler plutus-dashboard
sudo systemctl start   plutus-api plutus-scheduler plutus-dashboard

sudo systemctl status plutus-api plutus-scheduler plutus-dashboard postgresql --no-pager
```

`plutus-scheduler` and `plutus-dashboard` are ordered `After=plutus-api.service`.

---

## Step 9: OCI Firewall (Ingress Rules)

In OCI Console → Networking → VCN → Security Lists:

| Protocol | Source | Port | Description |
|---|---|---|---|
| TCP | 0.0.0.0/0 | 8000 | FastAPI |
| TCP | 0.0.0.0/0 | 8501 | Streamlit Dashboard |

```bash
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 8501/tcp
sudo ufw enable
```

The FastAPI layer is token-authenticated (`API_TOKEN` in `.env`); only `/healthz` and `/version` are unauthenticated. Consider fronting `:8000` behind the Cloudflare Tunnel rather than opening it publicly.

---

## Step 10: Cloudflare Tunnel (Free Public URL)

### MVP — free `*.trycloudflare.com`

```bash
cloudflared tunnel --url http://localhost:8501
```

### Production — named tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create plutus
cloudflared tunnel route dns plutus plutus.your-domain.com

sudo mkdir -p /etc/cloudflared
sudo cp /home/ubuntu/plutus-app/deployment/cloudflared.yml /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml   # set credentials-file to your tunnel UUID

sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

---

## Monitoring & Maintenance

### Status

```bash
sudo systemctl status plutus-api plutus-scheduler plutus-dashboard postgresql cloudflared --no-pager
```

### Logs

```bash
sudo journalctl -u plutus-api -f
sudo journalctl -u plutus-scheduler -f
sudo journalctl -u plutus-dashboard -f
sudo journalctl -u plutus-api -n 200 --no-pager
```

### Restart after a code update

```bash
cd /home/ubuntu/plutus-app
git pull            # or rsync from Mac
source .venv/bin/activate
pip install -e .    # if dependencies changed
sudo systemctl restart plutus-api plutus-scheduler plutus-dashboard
```

### Database backup

```bash
mkdir -p /home/ubuntu/backups
pg_dump -U plutus -h 127.0.0.1 plutus_db \
    > /home/ubuntu/backups/plutus_$(date -u +%Y%m%d).sql
```

---

## Resource Monitor

```bash
free -h
top -u ubuntu
df -h
```

Expected idle footprint with all three services running:

| Component | Idle RAM |
|---|---|
| postgresql | ~80 MB |
| plutus-api (FastAPI/uvicorn) | ~150 MB |
| plutus-scheduler (APScheduler) | ~90 MB |
| plutus-dashboard (Streamlit) | ~150 MB |
| cloudflared | ~20 MB |
| **Total** | **≈ 490 MB / 12 GB** |

---

## ARM64-Specific Notes

All v2 runtime dependencies are pure Python or ship ARM64 wheels:

- `fastapi` / `uvicorn` / `apscheduler` / `streamlit` — pure Python ✅
- `sqlalchemy` / `pydantic` / `pydantic-settings` — ARM64 wheels ✅
- `pandas` / `numpy` / `scipy` — ARM64 wheels ✅
- `psycopg` (for the Postgres `DB_URL`) — ARM64 wheel ✅

v2 does **not** use `backtrader`, `pandas-ta`, `langgraph`, or `ta-lib`; the backtest, indicators, and scoring are implemented in-tree.

---

## Cost Summary

| Resource | Cost |
|---|---|
| OCI A1.flex 2 OCPU / 12 GB | Free (Always Free tier) |
| PostgreSQL 16 (self-hosted) | Free |
| Streamlit (self-hosted) | Free |
| Market data / news (free tiers) | Free |
| Telegram Bot API | Free |
| Cloudflare Tunnel | Free |
| OpenRouter (color-only LLM narration) | ~$2–10 / month |
| **Total** | **~$2–10 / month** |
