# Plutus v3 — Agent Handoff Document

> Last updated: 2026-06-25  
> Branch: `v3-UI-upgrade`  
> Live URL: https://collecting-ride-hang-below.trycloudflare.com *(temporary — changes on container restart)*  
> OCI server: `oracle-lee` (92.5.33.117) — SSH host alias in `~/.ssh/config`

---

## Stack Overview

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite 6 + TypeScript + Tailwind CSS v4 |
| State / fetching | TanStack Query v5 (`useQuery`, `useMutation`) + Zustand v5 auth store |
| HTTP client | Axios at `/api` base URL, Bearer token from Zustand auth store |
| Charts | TradingView Lightweight Charts v5 |
| Backend | FastAPI (Python 3.12) + Pydantic v2 + SQLAlchemy 2 (async-style sync sessions) |
| Database | PostgreSQL 16 (Docker volume `pgdata`) |
| Scheduler | APScheduler 3 (blocking, IST timezone) in a separate container |
| Deployment | Docker Compose (`deployment/docker-compose.yml`) |
| Public tunnel | `cloudflare/cloudflared` quick tunnel (`tunnel --url http://frontend:80`) |

---

## Repository Layout

```
plutus-app/
├── backend/
│   ├── Dockerfile               # multi-stage: base → api / scheduler targets
│   ├── pyproject.toml
│   ├── alembic/                 # DB migrations
│   │   └── versions/0ef8a817f493_initial_schema.py
│   └── src/plutus/
│       ├── api/
│       │   ├── main.py          # FastAPI app, router mounts
│       │   ├── shared.py        # /shared/* endpoints (regime, portfolio, chart, LTP, backtest…)
│       │   ├── swing.py         # /swing/* endpoints (signals, trades, fills)
│       │   ├── accumulation.py  # /accumulation/* endpoints
│       │   ├── auth.py          # Bearer token auth
│       │   ├── deps.py          # FastAPI dependency injectors
│       │   └── schemas/shared.py  # Pydantic response models
│       ├── data/providers/
│       │   └── angelone_provider.py  # Angel One SmartAPI wrapper (see Known Issues)
│       ├── scheduler/
│       │   ├── runner.py        # APScheduler setup
│       │   ├── jobs.py          # All pipeline job logic
│       │   └── triggers.py      # Cron trigger definitions
│       └── db/
│           ├── models.py        # SQLAlchemy ORM models
│           └── session.py       # Engine / session factory
├── frontend/
│   ├── Dockerfile               # node:20-alpine build → nginx:alpine serve
│   ├── nginx.conf               # /api/ proxy_pass → http://api:8007/
│   ├── vite.config.ts           # dev proxy → http://localhost:8007
│   └── src/
│       ├── api/
│       │   ├── client.ts        # Axios instance, base URL /api, Bearer injection
│       │   └── hooks.ts         # All TanStack Query hooks
│       ├── pages/               # One file per page/route
│       └── types/api.ts         # TypeScript interfaces matching backend schemas
└── deployment/
    ├── docker-compose.yml       # Main compose file (all services + cloudflared)
    ├── docker-compose.prod.yml  # Prod overlay (disables direct port, adds named tunnel)
    ├── .env.example             # Template — copy to .env and fill secrets
    ├── deploy.sh                # Idempotent deploy script for Ubuntu 22.04 ARM64
    └── cloudflared.yml          # Named tunnel config (requires Cloudflare account)
```

---

## Authentication

- Single shared Bearer token in `deployment/.env` → `API_TOKEN`
- Current value on OCI: `plutus-local-dev-token` *(change this for production use)*
- All API routes except `/healthz` and `/version` require `Authorization: Bearer <token>`
- Frontend stores the token in Zustand (`useAuthStore`) and persists it in `localStorage`
- Login page: enter token → `POST /auth/verify` → if 200, set authenticated

---

## Frontend Pages

| Page | Route | Key hooks used |
|---|---|---|
| Dashboard | `/` | `useRegime`, `usePortfolioSnapshot`, `useRunLog` |
| Signals | `/signals` | `useSignals`, `useSwingPositions`, `useEnterSignal`, `useLTP` |
| Positions | `/positions` | `usePortfolioSnapshot`, `useSwingPositions`, `useExitTrade`, `useLTP` |
| Candidates | `/candidates` | `useCandidates`, `useAccumulationPositions`, `useStartAccumulationPosition`, `useLTP` |
| Accum Positions | `/accum-positions` | `useAccumulationPositions` |
| Strategy Lab | `/strategy-lab` | `useCalibration`, `useSignals`, `useCandidates`, `useRunBacktest` |
| Calibration | `/calibration` | `useCalibration` |
| Postmortem | `/postmortem` | (direct API fetch) |
| Glossary | `/glossary` | (static) |

### Key UI patterns

- **Trade modal** (`Signals.tsx`): BUY/SELL toggle, CMP auto-fill via `useLTP`, signal levels grid (Entry / SL / T1 / T2 / R:R), live total cost preview. Sell button only visible if user owns the symbol (derived from open swing positions).
- **Exit modal** (`Positions.tsx`): shares-to-sell input, CMP from `useLTP`, total proceeds + realised P&L preview, 6 preset exit reasons + custom text.
- **Accumulation modal** (`Candidates.tsx`): shows tranche number, existing open positions for symbol, CMP pre-fill, note field.
- **Chart** (`StockChart.tsx`): LW Charts v5, floating legend (DMA 20 blue solid / DMA 50 amber solid / DMA 200 red dashed / BB bands / golden cross markers). Separate MACD pane with labelled header.
- **Candidates deduplication**: multiple pipeline runs create duplicate rows per symbol — frontend deduplicates by keeping the latest `created_at` per symbol before rendering.

---

## Backend API Endpoints

### `/shared/*`
| Method | Path | Notes |
|---|---|---|
| GET | `/shared/regime` | Returns latest regime snapshot or **`null`** (not 404) when DB is empty |
| GET | `/shared/portfolio-snapshot` | Live P&L across swing + accumulation positions |
| GET | `/shared/chart/{symbol}` | OHLCV + indicators (DMA/BB/MACD). Prefers Angel One, falls back to yfinance |
| GET | `/shared/ltp/{symbol}` | Live price. Returns 404 if unavailable — `useLTP` hook catches this and returns `null` |
| GET | `/shared/calibration` | All calibration rows (bucket × regime win rate / expectancy) |
| POST | `/shared/backtest` | Walk-forward backtest for a symbol + bundle. Body: `BacktestRequestIn`. Timeout 120s |
| GET | `/shared/run-log` | Recent pipeline run log entries |
| POST | `/shared/runs/sunday` | Manually trigger full Sunday pipeline |
| POST | `/shared/runs/monday-revalidation` | Manually trigger Monday revalidation |
| POST | `/shared/runs/midweek-mini` | Manually trigger midweek mini screen |

### `/swing/*`
| Method | Path | Notes |
|---|---|---|
| GET | `/swing/signals` | `?latest_run=true&dedup=true` recommended params |
| GET | `/swing/positions` | Open + T1-hit swing trades |
| POST | `/swing/signals/{id}/enter` | Body: `{side, qty, price}` — creates a trade from a signal |
| POST | `/swing/trades/{id}/exit/manual` | Body: `{reason}` — exits a trade |

### `/accumulation/*`
| Method | Path | Notes |
|---|---|---|
| GET | `/accumulation/candidates` | All accumulation candidates |
| POST | `/accumulation/positions` | Body: `{symbol, price, qty, note}` — start a new tranche |
| GET | `/accumulation/positions` | All accumulation positions |
| POST | `/accumulation/positions/{id}/pause` | Pause accumulation |
| POST | `/accumulation/positions/{id}/resume` | Resume accumulation |
| POST | `/accumulation/positions/{id}/exit` | Body: `{price, qty, reason}` — exit tranche |

---

## Scheduler Jobs (IST timezone)

| Job | Schedule | What it does |
|---|---|---|
| `sunday_full_run` | Sunday @ `SUNDAY_FULL_RUN_HOUR_IST` (default 19:00) | Full pipeline: regime detection, signal scoring, accumulation screen, calibration update |
| `monday_revalidation` | Monday @ `MONDAY_REVALIDATION_HOUR_IST:MINUTE` (default 09:10) | Re-validates open signals against current market |
| `daily_exit_monitor` | Mon–Fri @ 09:00, 09:15, 09:30, 10:00, 11:00, 13:00, 15:00 | Checks open trades for SL / T1 / T2 hits, updates state |
| `daily_freshness_check` | Daily | Checks data freshness, logs stale symbols |
| `midweek_mini_screen` | Wednesday | Lighter version of Sunday screen |
| `weekly_postmortem` | Friday evening | Publishes weekly trade postmortem |

---

## Deployment

### OCI Server (`oracle-lee`)

- **IP**: 92.5.33.117 — SSH via `oracle-lee` host alias
- **Key**: `/Users/leander/Downloads/key/re/oci/ssh-key-2026-05-28.key`
- **App dir**: `~/plutus-app`
- **Env file**: `~/plutus-app/deployment/.env` — contains all secrets, **never commit this**
- **Port 3000** is open in iptables but blocked by OCI Security List — use cloudflared tunnel instead
- **Port 80** same situation — accessible only via tunnel

### Running services
```bash
sudo docker compose -f ~/plutus-app/deployment/docker-compose.yml ps
```

### Update and redeploy
```bash
ssh oracle-lee
cd ~/plutus-app
git pull origin v3-UI-upgrade
cd deployment
sudo docker compose up -d --build   # rebuilds images and restarts changed services
```

### Get current tunnel URL
```bash
ssh oracle-lee "sudo docker logs plutus-cloudflared-1 2>&1 | grep trycloudflare"
```

### Database backup/restore
```bash
# Dump from local
docker exec plutus-db-1 pg_dump -U plutus -d plutus_db --no-owner -Fc -f /tmp/dump.pgdump

# Restore to OCI
scp /tmp/dump.pgdump oracle-lee:/tmp/
ssh oracle-lee "sudo docker cp /tmp/dump.pgdump plutus-db-1:/tmp/ && \
  sudo docker exec plutus-db-1 pg_restore -U plutus -d plutus_db --no-owner --clean --if-exists -Fc /tmp/dump.pgdump"
```

### .env required keys
```
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
API_TOKEN               # Bearer token for all API calls
ANGEL_API_KEY           # Angel One SmartAPI key
ANGEL_CLIENT_ID         # Angel One client ID
ANGEL_PASSWORD          # Angel One login password
ANGEL_TOTP_SECRET       # TOTP secret (pyotp) for 2FA
TELEGRAM_BOT_TOKEN      # Optional — Telegram alerts
TELEGRAM_CHAT_ID        # Optional
OPENROUTER_API_KEY      # Optional — LLM-based signal narration
TOTAL_CAPITAL_INR       # Portfolio size for position sizing
FRONTEND_PORT           # Host port for nginx (default 80)
```

---

## Angel One Integration

File: `backend/src/plutus/data/providers/angelone_provider.py`

### Session management (fixed this session)
- `generateSession()` stores `jwtToken` + `refreshToken` in module-level `_SESSION_CACHE`
- On any `status: False` API response: calls `invalidate_session()` (keeps `refresh_token`), retries
- Retry #1: calls `generateToken(refresh_token)` — JWT renewal without TOTP
- Retry #2 (if token renewal also fails): full `generateSession()` with fresh TOTP code
- `fetch_ltp` and `_getCandleData` both follow this 2-attempt pattern

### Known issue on OCI
`ModuleNotFoundError: No module named 'websocket'` — the `smartapi-python` package's `__init__.py` imports `SmartWebSocket` which depends on `websocket-client`. This import happens at module level so Angel One LTP calls currently fail on OCI. The fix is:
```bash
ssh oracle-lee "sudo docker exec plutus-api-1 pip install websocket-client"
```
But this is lost on container rebuild. Proper fix: add `websocket-client` to `backend/pyproject.toml` dependencies.

### Price fetch cascade
`_fetch_live_prices(symbols)` in `shared.py`:
1. Angel One `fetch_ltp_batch` (fastest, real-time)
2. yfinance for any still-missing symbols (fallback, may be throttled)
3. `LatestPrice` DB table (stale cache, last successful fetch) for any still-missing

---

## Known Bugs / Issues

| # | Issue | Location | Workaround |
|---|---|---|---|
| 1 | `websocket-client` missing in Docker image breaks Angel One LTP | `pyproject.toml` | `pip install websocket-client` in running container; add to deps permanently |
| 2 | Cloudflare quick tunnel URL changes on container restart | `docker-compose.yml` | Check logs for new URL. Permanent fix: set up named Cloudflare tunnel |
| 3 | OCI port 80/3000 not reachable directly (OCI Security List + host iptables conflict) | OCI networking | Use cloudflared tunnel only |
| 4 | Candidates page shows duplicates if backend doesn't deduplicate | `Candidates.tsx` | Frontend deduplicates by keeping latest `created_at` per symbol — backend should deduplicate at DB/API level instead |
| 5 | `useRunBacktest` hook times out on large lookback windows (>365d) | `hooks.ts` | Axios timeout set to 120s; backend backtest is synchronous and may exceed this |
| 6 | Strategy Lab backtest only supports synthetic SIDEWAYS regime | `backtest_service.py` | Labelled as "display only, not evidence for live sizing" in UI |
| 7 | `seed_demo_data.py` uses deprecated `datetime.utcnow()` | `scripts/seed_demo_data.py` | Cosmetic warning only, no functional impact |
| 8 | `/shared/regime` returns `null` when no pipeline has run yet | `shared.py` | Fixed — returns null with 200. Frontend should show "No regime data — run pipeline first" |
| 9 | Exit modal backend only accepts `reason` string (no price/qty) — manual fills not recorded | `swing.py` | Trade exit records no fill for the exit leg; P&L is derived from entry fills only |

---

## Future Development / Improvement Plans

### High priority
- **Add `websocket-client` to `pyproject.toml`** so Angel One works out of the box post-rebuild
- **Named Cloudflare tunnel** (requires Cloudflare account + tunnel UUID + credentials JSON) — replace quick tunnel with a stable URL
- **Backend-level candidate deduplication** — SQL `DISTINCT ON (symbol)` query keyed on latest `created_at` instead of frontend dedup
- **Exit fills** — record a SELL fill when a trade is manually exited so P&L history is accurate

### Medium priority
- **Regime badge on Dashboard** — show "No data" state gracefully when regime is null (currently may show blank)
- **Push notifications** — Telegram alerts for SL hits / T1 hits are wired in the scheduler but `TELEGRAM_BOT_TOKEN` needs to be set
- **Position sizing calculator** — show recommended lot size per signal based on `TOTAL_CAPITAL_INR` and SL distance
- **Pagination on Signals page** — 304 signals renders fine but will degrade; add virtual scrolling or pagination
- **Chart performance** — LW Charts redraws on every `useQuery` refetch; memoize chart data

### Low priority / Nice-to-have
- **Merge `v3-UI-upgrade` branch into `main`** — current prod is running off `v3-UI-upgrade`; main is stale
- **CI/CD pipeline** — GitHub Actions: lint + typecheck on PR, auto-build + push image on merge to main
- **yfinance rate limiting** — add exponential backoff retry; currently silent fails become stale cache reads
- **Real walk-forward backtest** — `backtest_service.py` uses synthetic signals; wire to actual Sunday pipeline output for true out-of-sample validation
- **Accumulation exit modal** — `AccumulationPositions.tsx` has a basic exit button but no proper modal like Positions page has
- **Dark/light theme toggle** — CSS variables are set up for theming; theme switcher not yet in UI

---

## Local Development

```bash
# Start all services
cd deployment && docker compose up -d

# Frontend hot-reload dev server (proxies /api to localhost:8007)
cd frontend && npm run dev

# Rebuild and redeploy frontend to running nginx container
cd frontend && npm run build && docker cp dist/. plutus-frontend-1:/usr/share/nginx/html/ && docker exec plutus-frontend-1 nginx -s reload

# Hot-patch backend without rebuild
# 1. Edit the file locally
# 2. Find installed path: docker exec plutus-api-1 python3 -c "import plutus.api.shared; print(plutus.api.shared.__file__)"
# 3. docker cp <edited_file> plutus-api-1:<installed_path>
# 4. docker restart plutus-api-1

# Seed demo data (fresh DB)
docker exec plutus-api-1 python3 /app/scripts/seed_demo_data.py

# Run Sunday pipeline manually
curl -X POST http://localhost:8007/shared/runs/sunday -H "Authorization: Bearer plutus-local-dev-token"
```

---

## Git State

- **Active branch**: `v3-UI-upgrade`
- **Remote**: `https://github.com/leandercibi/plutus-app.git`
- **`main` branch**: stale (pre-v3 Streamlit code) — do not deploy from main
- All v3 work is on `v3-UI-upgrade`; merge to main when ready for a clean release
