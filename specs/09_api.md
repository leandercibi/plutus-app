# 09 — FastAPI Routes (Hermes Integration)

> 3 routes total. Lightweight. Runs in-process with the scheduler in `plutus-main.service`.
> Per-API-key rate limit (slowapi, in-memory) + 5-minute symbol cache (in-memory).

---

## Route Summary

| Method | Path | Auth | Rate-limited | Cached |
|---|---|---|---|---|
| `POST` | `/analyze` | `X-API-Key` | yes (`API_RATE_LIMIT_PER_HOUR/hour` per key) | yes (5 min, by `(symbol, exchange)`) |
| `GET` | `/weekly` | `X-API-Key` | no | no |
| `GET` | `/health` | none | no | no |

---

## `plutus/api/cache.py` — 5-minute symbol cache

Shared by `/analyze` (HTTP), the Telegram `/stock SYMBOL` command, and the dashboard "Run on-demand analysis" button. In-memory; cleared on process restart (acceptable for MVP).

```python
# plutus/api/cache.py
from threading import Lock
import time
from plutus.config import settings
from plutus.agents.graph import run_analysis

_CACHE: dict[tuple, tuple[float, dict]] = {}
_LOCK = Lock()


def analyze_with_cache(symbol: str, exchange: str = "NSE") -> dict:
    key = (symbol.upper(), exchange.upper())
    now = time.time()
    with _LOCK:
        if key in _CACHE and (now - _CACHE[key][0]) < settings.ANALYZE_CACHE_TTL_SECONDS:
            res = dict(_CACHE[key][1])
            res["cache_hit"] = True
            return res
    result = run_analysis(symbol, exchange)
    result["cache_hit"] = False
    with _LOCK:
        _CACHE[key] = (now, dict(result))
    return result
```

Notes:
- The cache stores a deep-ish copy (`dict(result)`) so the per-call `cache_hit` flag mutation does not poison the cache entry.
- Evictions are passive (next read after TTL expiry overwrites the slot). For MVP we do not garbage-collect stale keys; memory pressure is bounded by the universe size (~200 symbols × ~3 KB ≈ 600 KB).
- `run_analysis` already populates `entry_mid` and `analysis_time_sec` (see `08_agents.md`); the cache stores those alongside `cache_hit`.

---

## `plutus/api/routes.py`

```python
# plutus/api/routes.py
from __future__ import annotations

import hmac
import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from plutus.api.cache import analyze_with_cache
from plutus.config import settings
from plutus.db.models import Recommendation, WeeklyRun
from plutus.db.session import SessionLocal

router = APIRouter()

# Process boot time for /health uptime calculation.
_BOOT_TIME = time.time()


# ── Auth ─────────────────────────────────────────────────────────────────────

def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """
    Constant-time comparison against settings.API_SECRET_KEY.
    Raises 401 on missing or invalid header.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    expected = settings.API_SECRET_KEY or ""
    if not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ── Rate limiter ────────────────────────────────────────────────────────────

def _api_key_from_request(request: Request) -> str:
    """Bucket key for slowapi: the X-API-Key header value (per-key bucket)."""
    return request.headers.get("X-API-Key", "anonymous")


limiter = Limiter(key_func=_api_key_from_request)


# ── Request / Response Models ───────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="NSE/BSE symbol, e.g. RELIANCE, INFY, TATAMOTORS")
    exchange: str = Field("NSE", description="NSE or BSE")


class PositionModel(BaseModel):
    shares: int
    capital: float
    pct_of_portfolio: float
    max_loss_inr: float


class HoldDaysModel(BaseModel):
    min: int
    max: int


class SignalsModel(BaseModel):
    technical: dict
    sentiment: dict
    smart_money: dict


class AnalyzeResponse(BaseModel):
    symbol: str
    exchange: str
    current_price: float
    recommendation: str            # BUY | SELL | HOLD | WATCH | AVOID
    confidence: float              # 0–10
    entry_zone: List[float]        # [low, high]
    entry_mid: float               # = (low + high) / 2
    targets: List[float]           # [target1, target2]
    stop_loss: float
    risk_reward: float
    position: PositionModel
    hold_days: HoldDaysModel       # {"min": int, "max": int}
    strategy: str
    signals: SignalsModel
    risk_flags: List[str]
    reasoning: str
    cache_hit: bool
    analysis_time_sec: float


class WeeklyRecommendation(BaseModel):
    symbol: str
    recommendation: str
    confidence: float
    entry_zone: List[Optional[float]]
    entry_mid: Optional[float]
    targets: List[Optional[float]]
    stop_loss: Optional[float]
    hold_days: HoldDaysModel
    reasoning: str


class WeeklyResponse(BaseModel):
    run_date: str
    market_regime: str
    strategy_selected: str
    buy_signals: List[WeeklyRecommendation]
    watch_signals: List[WeeklyRecommendation]
    total_screened: int


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    uptime_seconds: float
    db_ok: bool


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(f"{settings.API_RATE_LIMIT_PER_HOUR}/hour")
async def analyze_stock(
    request: Request,
    response: Response,
    body: AnalyzeRequest,
    _: str = Depends(verify_api_key),
):
    """
    Run the full agent pipeline for a single stock (cached for 5 min per symbol).
    Used by Hermes as an AI tool. Cold-path latency: ~15-25 s; cache hit: <50 ms.
    """
    symbol = body.symbol.upper().strip()
    exchange = body.exchange.upper().strip()

    try:
        result = analyze_with_cache(symbol, exchange)
    except ValueError as e:
        # 422: symbol not found on the requested exchange.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # 503: upstream data fetch / LLM failure.
        raise HTTPException(status_code=503, detail=f"Analysis failed: {e}")

    # X-RateLimit-Remaining (slowapi populates state on the request).
    remaining = _remaining_for_request(request)
    if remaining is not None:
        response.headers["X-RateLimit-Remaining"] = str(remaining)

    entry_zone = result.get("entry_zone") or [0.0, 0.0]
    entry_mid = result.get("entry_mid")
    if entry_mid is None and len(entry_zone) == 2:
        entry_mid = round((float(entry_zone[0]) + float(entry_zone[1])) / 2, 2)

    return AnalyzeResponse(
        symbol=symbol,
        exchange=exchange,
        current_price=result.get("current_price", 0.0),
        recommendation=result.get("recommendation", "HOLD"),
        confidence=result.get("confidence", 0.0),
        entry_zone=entry_zone,
        entry_mid=float(entry_mid or 0.0),
        targets=result.get("targets", [0.0, 0.0]),
        stop_loss=result.get("stop_loss", 0.0),
        risk_reward=result.get("risk_reward", 0.0),
        position=PositionModel(
            **result.get(
                "position",
                {"shares": 0, "capital": 0.0, "pct_of_portfolio": 0.0, "max_loss_inr": 0.0},
            )
        ),
        hold_days=HoldDaysModel(
            min=int(result.get("hold_days_min", 5)),
            max=int(result.get("hold_days_max", 8)),
        ),
        strategy=result.get("strategy", ""),
        signals=SignalsModel(
            technical=result.get("technical_output", {}),
            sentiment=result.get("sentiment_output", {}),
            smart_money=result.get("smart_money_output", {}),
        ),
        risk_flags=result.get("risk_flags", []),
        reasoning=result.get("reasoning", ""),
        cache_hit=bool(result.get("cache_hit", False)),
        analysis_time_sec=float(result.get("analysis_time_sec", 0.0)),
    )


@router.get("/weekly", response_model=WeeklyResponse)
async def get_weekly_recommendations(_: str = Depends(verify_api_key)):
    """
    Return the latest weekly_runs row plus its recommendations.
    Pre-computed; no LLM calls; sub-100 ms.
    """
    with SessionLocal() as db:
        latest_run = (
            db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        )
        if not latest_run:
            raise HTTPException(status_code=404, detail="No weekly run found yet")

        recs = (
            db.query(Recommendation)
            .filter(Recommendation.weekly_run_id == latest_run.id)
            .order_by(Recommendation.confidence.desc())
            .all()
        )

        def _to_model(r: Recommendation) -> WeeklyRecommendation:
            return WeeklyRecommendation(
                symbol=r.symbol,
                recommendation=r.recommendation.value if hasattr(r.recommendation, "value") else str(r.recommendation),
                confidence=r.confidence or 0.0,
                entry_zone=[r.entry_low, r.entry_high],
                entry_mid=float(r.entry_mid) if r.entry_mid is not None else None,
                targets=[r.target1, r.target2],
                stop_loss=r.stop_loss,
                hold_days=HoldDaysModel(
                    min=int(r.hold_days_min or 5),
                    max=int(r.hold_days_max or 8),
                ),
                reasoning=r.reasoning_text or "",
            )

        buy_signals = [_to_model(r) for r in recs if _verdict(r) == "BUY"]
        watch_signals = [_to_model(r) for r in recs if _verdict(r) == "WATCH"]

        return WeeklyResponse(
            run_date=str(latest_run.run_date),
            market_regime=latest_run.market_regime or "UNKNOWN",
            strategy_selected=latest_run.strategy_selected or "",
            buy_signals=buy_signals,
            watch_signals=watch_signals,
            total_screened=latest_run.stocks_screened or 0,
        )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Liveness + DB connectivity check. No auth required."""
    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        service="Plutus Trading Engine",
        timestamp=datetime.utcnow().isoformat(),
        uptime_seconds=round(time.time() - _BOOT_TIME, 1),
        db_ok=db_ok,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _verdict(r: Recommendation) -> str:
    v = r.recommendation
    return v.value if hasattr(v, "value") else str(v)


def _remaining_for_request(request: Request) -> Optional[int]:
    """
    Best-effort read of slowapi's per-request remaining counter.
    slowapi attaches `view_rate_limit` to request.state on a successful pass.
    """
    rl = getattr(request.state, "view_rate_limit", None)
    if rl is None:
        return None
    # slowapi stores (limit, remaining, reset) in different shapes across versions;
    # we defensively probe.
    try:
        if isinstance(rl, tuple) and len(rl) >= 2:
            return int(rl[1])
        return int(getattr(rl, "remaining"))
    except Exception:
        return None
```

---

## Rate-limit handler (429 body shape)

slowapi raises `RateLimitExceeded`; we wire a custom handler so the response body matches the contract: `{"error": "rate_limit_exceeded", "retry_after_seconds": <int>}` plus a `Retry-After` header.

```python
# plutus/api/rate_limit.py
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # slowapi exposes the limit object on the exception; reset_at - now ≈ retry_after.
    retry_after = _retry_after_seconds(exc)
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    # exc.detail is a string like "30 per 1 hour"; we cannot derive an exact reset
    # time from it. We fall back to a 60-second hint, which is conservative for an
    # hourly bucket. If the slowapi version exposes `exc.limit.reset_at`, we use it.
    try:
        reset_at = getattr(exc.limit, "reset_at", None)
        if reset_at is not None:
            import time as _t
            delta = int(reset_at - _t.time())
            return max(1, delta)
    except Exception:
        pass
    return 60
```

---

## FastAPI App Wiring (in `src/main.py`)

```python
# src/main.py (excerpt)
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from plutus.api.routes import router as api_router, limiter
from plutus.api.rate_limit import rate_limit_handler
from plutus.config import settings

app = FastAPI(title="Plutus Trading Engine", version="1.0.0")

# Rate limiter wiring: required by slowapi.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.include_router(api_router)

# uvicorn launched from main.py (see 12_scheduler.md / 15_deployment.md):
import uvicorn  # noqa: E402
uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
```

---

## Error Responses

| Code | When | Body |
|---|---|---|
| 200 | Success | model body |
| 401 | Missing or invalid `X-API-Key` | `{"detail": "Missing X-API-Key header"}` or `{"detail": "Invalid API key"}` |
| 404 | `/weekly` called before any weekly run has completed | `{"detail": "No weekly run found yet"}` |
| 422 | `/analyze` called with a symbol not found on the requested exchange | `{"detail": "<reason>"}` |
| 429 | Per-key rate limit exceeded on `/analyze` | `{"error": "rate_limit_exceeded", "retry_after_seconds": <int>}` + `Retry-After` header |
| 503 | Upstream data fetch / LLM failure | `{"detail": "Analysis failed: <reason>"}` |

`/analyze` response also sets `X-RateLimit-Remaining: <int>` on 200.

---

## Hermes Agent Tool Definition

Give this JSON to your Hermes agent as a tool:

```json
[
  {
    "type": "function",
    "function": {
      "name": "analyze_stock",
      "description": "Analyze an Indian NSE/BSE stock and return a buy/sell/hold recommendation with entry zone, entry mid, targets, stop loss, position size, and reasoning. Cold call ~15-25 s; cached calls within 5 min are <50 ms.",
      "parameters": {
        "type": "object",
        "properties": {
          "symbol": {
            "type": "string",
            "description": "NSE/BSE ticker symbol in uppercase. Examples: RELIANCE, INFY, TATAMOTORS, HDFCBANK, TCS"
          },
          "exchange": {
            "type": "string",
            "enum": ["NSE", "BSE"],
            "default": "NSE",
            "description": "Stock exchange. Default NSE."
          }
        },
        "required": ["symbol"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "get_weekly_picks",
      "description": "Get this week's BUY and WATCH signals from the latest automated weekly run. Pre-computed; responds in <100 ms.",
      "parameters": {"type": "object", "properties": {}, "required": []}
    }
  }
]
```

### Hermes HTTP Call Pattern (Python)

```python
# In your Hermes agent's tool executor:
import requests

PLUTUS_BASE = "http://<OCI_IP>:8000"
PLUTUS_KEY = "<your_api_secret_key>"


def analyze_stock(symbol: str, exchange: str = "NSE") -> dict:
    resp = requests.post(
        f"{PLUTUS_BASE}/analyze",
        headers={"X-API-Key": PLUTUS_KEY},
        json={"symbol": symbol, "exchange": exchange},
        timeout=60,
    )
    if resp.status_code == 429:
        retry = int(resp.headers.get("Retry-After", "60"))
        raise RuntimeError(f"Rate-limited; retry in {retry}s")
    resp.raise_for_status()
    body = resp.json()
    body["_rate_limit_remaining"] = int(resp.headers.get("X-RateLimit-Remaining", "-1"))
    return body


def get_weekly_picks() -> dict:
    resp = requests.get(
        f"{PLUTUS_BASE}/weekly",
        headers={"X-API-Key": PLUTUS_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

### curl

```bash
# /analyze (cold ~15-25 s)
curl -sS -X POST http://<OCI_IP>:8000/analyze \
  -H "X-API-Key: $PLUTUS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "RELIANCE", "exchange": "NSE"}' \
  | jq

# /weekly
curl -sS http://<OCI_IP>:8000/weekly \
  -H "X-API-Key: $PLUTUS_API_KEY" | jq

# /health (no auth)
curl -sS http://<OCI_IP>:8000/health | jq
```

### Sample `/analyze` 200 response (truncated)

```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "current_price": 2845.30,
  "recommendation": "BUY",
  "confidence": 7.4,
  "entry_zone": [2820.0, 2860.0],
  "entry_mid": 2840.0,
  "targets": [2960.0, 3050.0],
  "stop_loss": 2780.0,
  "risk_reward": 2.1,
  "position": {
    "shares": 12,
    "capital": 34140.0,
    "pct_of_portfolio": 34.14,
    "max_loss_inr": 720.0
  },
  "hold_days": {"min": 5, "max": 8},
  "strategy": "trend + breakout",
  "signals": { "technical": {"...": "..."}, "sentiment": {"...": "..."}, "smart_money": {"...": "..."} },
  "risk_flags": [],
  "reasoning": "Trend bundle confirms with EMA50 rising and price holding above EMA21...",
  "cache_hit": false,
  "analysis_time_sec": 18.7
}
```

Response headers:

```
X-RateLimit-Remaining: 29
```

### Sample `/analyze` 429 response

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 1820
Content-Type: application/json

{"error": "rate_limit_exceeded", "retry_after_seconds": 1820}
```
