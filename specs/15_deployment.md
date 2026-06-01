# 15 — Deployment (OCI A1.flex, ARM64)

> **Service split.** Plutus runs as **three** application services plus
> PostgreSQL on a single OCI A1.flex VM. See `_CHANGE_SPEC.md` §9.
> - `plutus-main.service` — FastAPI + APScheduler (5 jobs) — `python main.py`
> - `plutus-bot.service` — Telegram polling + loopback `/push/*` API on `127.0.0.1:8001` — `python bot.py`
> - `plutus-dashboard.service` — Streamlit on `:8501` — `streamlit run dashboard.py`
> - `postgresql.service` (system)

---

## Instance Specs

- **Shape:** VM.Standard.A1.Flex
- **OCPUs:** 2
- **RAM:** 12 GB
- **OS:** Ubuntu 22.04 LTS (ARM64 / aarch64)
- **Storage:** 50 GB boot volume (minimum)

---

## Step 1: Initial OCI Instance Setup

```bash
# SSH into your instance
ssh ubuntu@<OCI_PUBLIC_IP>

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
python3.11 --version   # should show 3.11.x
```

---

## Step 2: PostgreSQL Setup

```bash
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
psql -U plutus -d plutus_db -h 127.0.0.1 -c "SELECT version();"
```

---

## Step 3: Clone / Upload Project

```bash
# Option A: Git
git clone https://github.com/yourusername/plutus-app.git /home/ubuntu/plutus-app

# Option B: rsync from your Mac
# Run this on your Mac, not the OCI instance:
rsync -avz /Users/leander/personal-projects/plutus-app/ \
    ubuntu@<OCI_IP>:/home/ubuntu/plutus-app/
```

The deployed tree is rooted at `/home/ubuntu/plutus-app/`. All Python lives
under `/home/ubuntu/plutus-app/src/`.

---

## Step 4: Python Environment

```bash
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
```

---

## Step 5: Environment Variables

```bash
# Create .env from the template in 03_config_env.md
nano /home/ubuntu/plutus-app/src/.env
# Paste and fill in your .env content from 03_config_env.md

# Secure it
chmod 600 /home/ubuntu/plutus-app/src/.env
```

---

## Step 6: Initialize Database

```bash
cd /home/ubuntu/plutus-app/src
source .venv/bin/activate

python -m plutus.db.init_db
# Expected output: "All tables created."
```

---

## Step 7: Test Run (Before Setting Up Services)

```bash
cd /home/ubuntu/plutus-app/src
source .venv/bin/activate

# Test the agent pipeline end-to-end
python -c "
from plutus.agents.graph import run_analysis
r = run_analysis('RELIANCE', 'NSE', use_cache=False)
print(r['recommendation'], r.get('confidence'))
"

# Test that plutus-main starts (Ctrl-C after a few seconds)
python main.py

# Test that plutus-bot starts (separate terminal; Ctrl-C after a few seconds)
python bot.py

# Test that plutus-dashboard renders (separate terminal)
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
```

---

## Step 8: Systemd Services

### Cron-time / IST sanity note

Plutus relies on the **APScheduler `timezone=IST` argument exclusively** —
every `CronTrigger` in `main.py` is constructed with `timezone=IST` and the
scheduler itself is built with `timezone=IST`. The host's wall clock is left
in UTC, the OCI default. We deliberately **do not** set
`Environment=TZ=Asia/Kolkata` in the unit files because mixing process-local
TZ with explicit `pytz` triggers is the easiest way to get phantom
double-shifts. One source of truth, in code.

(`pg_dump` filenames will be in UTC — that's intended; consistent across
backups regardless of host.)

### Service 1: `plutus-main` (FastAPI + APScheduler)

```bash
sudo nano /etc/systemd/system/plutus-main.service
```

```ini
# /etc/systemd/system/plutus-main.service
[Unit]
Description=Plutus — Main (FastAPI + Scheduler)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/plutus-app/src
Environment=PATH=/home/ubuntu/plutus-app/src/.venv/bin
EnvironmentFile=/home/ubuntu/plutus-app/src/.env
ExecStart=/home/ubuntu/plutus-app/src/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Service 2: `plutus-bot` (Telegram + loopback push API)

```bash
sudo nano /etc/systemd/system/plutus-bot.service
```

```ini
# /etc/systemd/system/plutus-bot.service
[Unit]
Description=Plutus — Telegram Bot
After=network.target plutus-main.service
Requires=plutus-main.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/plutus-app/src
Environment=PATH=/home/ubuntu/plutus-app/src/.venv/bin
EnvironmentFile=/home/ubuntu/plutus-app/src/.env
ExecStart=/home/ubuntu/plutus-app/src/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Service 3: `plutus-dashboard` (Streamlit)

```bash
sudo nano /etc/systemd/system/plutus-dashboard.service
```

```ini
# /etc/systemd/system/plutus-dashboard.service
[Unit]
Description=Plutus — Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/plutus-app/src
Environment=PATH=/home/ubuntu/plutus-app/src/.venv/bin
EnvironmentFile=/home/ubuntu/plutus-app/src/.env
ExecStart=/home/ubuntu/plutus-app/src/.venv/bin/streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable and Start All Three

```bash
sudo systemctl daemon-reload

sudo systemctl enable plutus-main plutus-bot plutus-dashboard
sudo systemctl start  plutus-main plutus-bot plutus-dashboard

# Verify
sudo systemctl status plutus-main plutus-bot plutus-dashboard postgresql --no-pager
```

`plutus-bot.service` is ordered `After=plutus-main.service` so the bot's
internal HTTP client never tries to reach a not-yet-bound port on first boot.
The bot itself only binds `127.0.0.1:8001` for `/push/*` — there is no public
ingress for that port.

---

## Step 9: OCI Firewall (Ingress Rules)

In OCI Console → Networking → Virtual Cloud Networks → Security Lists:

| Protocol | Source | Port | Description |
|---|---|---|---|
| TCP | 0.0.0.0/0 | 8000 | FastAPI (`/analyze` API) |
| TCP | 0.0.0.0/0 | 8501 | Streamlit Dashboard |

`8001` is **not** opened — `plutus-bot` binds it on the loopback only.

Also open the Ubuntu firewall:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 8501/tcp
sudo ufw enable
```

---

## Step 10: Cloudflare Tunnel (Free Public URL)

Cloudflare Tunnel gives the dashboard a public URL without exposing the OCI
IP and without needing a domain.

### MVP — free `*.trycloudflare.com` (no Cloudflare account)

```bash
# Quick anonymous tunnel — prints a https://xxxx.trycloudflare.com URL.
# Good enough for personal MVP usage; rotates on restart.
cloudflared tunnel --url http://localhost:8501
```

### Production — named tunnel (requires free Cloudflare account)

```bash
cloudflared tunnel login
cloudflared tunnel create plutus

# Map a hostname (your-domain.com on your Cloudflare zone) to localhost:8501
cloudflared tunnel route dns plutus plutus.your-domain.com

# Config file
sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yml >/dev/null <<'EOF'
tunnel: plutus
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL-UUID>.json
ingress:
  - hostname: plutus.your-domain.com
    service: http://localhost:8501
  - service: http_status:404
EOF

# Install as a systemd service
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

---

## Monitoring & Maintenance

### Status of all services

```bash
sudo systemctl status \
    plutus-main plutus-bot plutus-dashboard \
    postgresql cloudflared --no-pager
```

### Tail journal logs per service

```bash
# plutus-main (scheduler + API)
sudo journalctl -u plutus-main -f

# plutus-bot (Telegram + push API)
sudo journalctl -u plutus-bot -f

# plutus-dashboard (Streamlit)
sudo journalctl -u plutus-dashboard -f

# postgres / cloudflared
sudo journalctl -u postgresql -f
sudo journalctl -u cloudflared -f

# Last 200 lines, no follow
sudo journalctl -u plutus-main -n 200 --no-pager
```

### Restart after a code update

```bash
cd /home/ubuntu/plutus-app
git pull   # or rsync from Mac

sudo systemctl restart plutus-main plutus-bot plutus-dashboard
```

(Restart `plutus-main` first — `plutus-bot` is ordered after it. Restarting
all three at once is fine; systemd will resolve the order.)

### Manually trigger jobs

See `12_scheduler.md → Manual Triggers`. Quick reference:

```bash
cd /home/ubuntu/plutus-app/src
source .venv/bin/activate
python -c "import asyncio; from main import weekly_pipeline; asyncio.run(weekly_pipeline())"
```

### Database backup

```bash
# Weekly backup (add to user crontab)
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
| plutus-main (FastAPI + scheduler, 5 jobs registered) | ~220 MB |
| plutus-bot (Telegram polling + loopback FastAPI on 8001) | ~30 MB |
| plutus-dashboard (Streamlit) | ~150 MB |
| cloudflared | ~20 MB |
| **Total** | **≈ 500 MB / 12 GB** |

CPU is <5% idle and ~80% during the Sunday weekly run (≈ 25 min).

---

## ARM64-Specific Notes

All packages in `requirements.txt` are pure Python or have ARM64 wheels:

- `pandas-ta` — pure Python ✅
- `backtrader` — pure Python ✅
- `langgraph` — pure Python ✅
- `psycopg2-binary` — ARM64 wheel available ✅
- `uvicorn` / `fastapi` / `apscheduler` — pure Python ✅
- `python-telegram-bot` — pure Python ✅
- DO NOT install `ta-lib` (C extension, ARM64 compilation is painful) — use
  `pandas-ta` instead.

---

## Cost Summary

| Resource | Cost |
|---|---|
| OCI A1.flex 2 OCPU / 12 GB | Free (Always Free tier) |
| PostgreSQL 16 (self-hosted) | Free |
| Streamlit (self-hosted) | Free |
| `yfinance` market data | Free |
| RSS / NewsAPI free tier | Free |
| Telegram Bot API | Free |
| Cloudflare Tunnel | Free |
| OpenRouter (DeepSeek V4 Flash, fast + reasoner) | ~$2–10 / month |
| **Total** | **~$2–10 / month** |
