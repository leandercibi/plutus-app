# 12 — API Layer

> FastAPI. Three routers — `shared`, `swing`, `accumulation`. Authentication is single-user token (the operator). No public endpoints. The dashboard and the Telegram bot are the only consumers.

---

## 1. Module layout

```
src/plutus/api/
├── __init__.py
├── main.py                  # FastAPI app, includes routers
├── auth.py                  # token bearer; settings.api_token
├── deps.py                  # session dependency, settings dependency
├── shared.py                # /shared/* router
├── swing.py                 # /swing/* router
├── accumulation.py          # /accumulation/* router
├── schemas/
│   ├── shared.py
│   ├── swing.py
│   └── accumulation.py
└── errors.py                # uniform error envelope
```

---

## 2. Auth

```python
def require_token(authorization: str = Header(...)) -> None:
    if authorization != f"Bearer {get_settings().api_token.get_secret_value()}":
        raise HTTPException(401)
```

Applied as a dependency on every router. Health check (`/healthz`) and version (`/version`) are the only unauthenticated routes.

---

## 3. Schemas

All request/response bodies are Pydantic models in `schemas/`. No raw dicts crossing the boundary. Date fields are ISO 8601. Decimal fields are stringified (`"6420.50"`) to avoid float drift in JSON.

Example:

```python
class SwingSignalOut(BaseModel):
    id: int
    symbol: str
    bundle: str
    score: int
    label: Literal["BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"]
    entry: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    expectancy_R: float
    drawn_rr: float
    regime_at_signal: str
    pillar_breakdown: PillarBreakdownOut
    counterfactual: str | None
    calibration_band: Literal["low", "medium", "high"]
    created_at: datetime

    model_config = ConfigDict(json_encoders={Decimal: str})
```

---

## 4. Routes

### 4.1 `/shared`
| Verb | Path | Body / Query | Response | Notes |
|---|---|---|---|---|
| GET | `/healthz` | — | `{"ok": true}` | unauth |
| GET | `/version` | — | `{"version": "..."}` | unauth |
| GET | `/regime` | — | `RegimeVerdictOut` | latest |
| GET | `/regime/history` | `?days=30` | `list[RegimeSnapshotOut]` | |
| GET | `/universe` | `?as_of=YYYY-MM-DD` | `list[str]` | PIT lookup |
| GET | `/calibration/{bucket}/{regime}` | — | `CalibrationRowOut` | |
| GET | `/benchmarks/latest` | — | `BenchmarkResultOut` | |
| POST | `/runs/sunday` | — | `{"run_id": "..."}` | triggers Sunday batch |
| POST | `/runs/monday-revalidation` | — | `{"run_id": "..."}` | |
| POST | `/runs/midweek-mini` | — | gated by `settings.midweek_mini_screen_enabled` |

### 4.2 `/swing`
| Verb | Path | Body / Query | Response | Notes |
|---|---|---|---|---|
| GET | `/signals` | `?run_id=&label=` | `list[SwingSignalOut]` | |
| GET | `/signals/{id}` | — | `SwingSignalOut` | |
| GET | `/positions` | — | `list[SwingTradeOut]` | open + recently closed |
| POST | `/trades/{id}/fills/real` | `RealFillIn` | `FillOut` | B10 — user logs actual fill |
| POST | `/trades/{id}/exit/manual` | `{"reason": "..."}` | `SwingTradeOut` | manual close |
| GET | `/postmortem/latest` | — | `PostmortemOut` | |
| GET | `/cooldowns/{symbol}` | — | `list[CooldownRowOut]` | A16 visibility |

### 4.3 `/accumulation`
| Verb | Path | Body / Query | Response | Notes |
|---|---|---|---|---|
| GET | `/candidates` | `?run_id=` | `list[AccumulationCandidateOut]` | |
| GET | `/positions` | — | `list[AccumulationPositionOut]` | |
| GET | `/positions/{id}/tranches` | — | `list[TrancheOut]` | |
| POST | `/positions/{id}/pause` | `{"reason": "..."}` | `AccumulationPositionOut` | revalidation override |
| POST | `/positions/{id}/resume` | — | `AccumulationPositionOut` | |
| POST | `/positions/{id}/convert-to-swing` | — | `SwingTradeOut` | bull-ready voluntary |

---

## 5. Error envelope (`errors.py`)

```python
class ErrorOut(BaseModel):
    code: str
    message: str
    request_id: str

@app.exception_handler(HTTPException)
def http_handler(req, exc): ...

@app.exception_handler(Exception)
def fallback(req, exc): ...   # 500 with sanitized message; full trace in logs
```

---

## 6. Idempotency

Run-trigger endpoints (`/runs/*`) accept an optional `Idempotency-Key` header. The server records `(key, run_id)` for 24h; duplicate keys return the prior `run_id` instead of re-running.

---

## 7. Tests (`tests/api/`)

| Test file | Cases |
|---|---|
| `test_auth.py` | Bearer required; missing or wrong → 401. `/healthz` and `/version` allowed without. |
| `test_shared_regime.py` | Returns latest snapshot; matches DB fixture. |
| `test_shared_universe_pit.py` | Past `as_of` returns frozen membership. |
| `test_shared_calibration.py` | CI fields present in response. |
| `test_shared_runs_sunday.py` | Triggers scheduler; returns run_id. Idempotency key honored. |
| `test_swing_signals_filter.py` | `?label=BUY` filters correctly. |
| `test_swing_positions.py` | Open and recently closed within 7d returned. |
| `test_swing_real_fill_post.py` | Insert REAL fill → returned; calibration query prefers it. |
| `test_swing_manual_exit.py` | Trade state updates to CLOSED_*; alert NOT re-fired. |
| `test_swing_cooldowns.py` | Returns separate rows per kind (A16 cross-ref). |
| `test_accumulation_candidates.py` | Schema matches; hard_avoid_active reflected. |
| `test_accumulation_tranches.py` | Ordered by seq. |
| `test_accumulation_pause_resume.py` | State transitions correct; resume requires reason on prior pause. |
| `test_accumulation_convert_to_swing.py` | Creates SwingTrade; AccumulationPosition.state=CONVERTED_TO_SWING. |
| `test_error_envelope.py` | 500 returns ErrorOut shape, not stack trace. |
| `test_decimal_json_roundtrip.py` | Decimals come back as strings; client can re-parse losslessly. |

All tests use FastAPI's `TestClient` with a SQLite test DB.

---

## Acceptance criteria

- [ ] Every endpoint in §4 exists with its schema.
- [ ] All tests pass.
- [ ] OpenAPI spec generated at `/docs` shows full schemas (no `Any` types).
- [ ] No endpoint mutates state without an explicit POST.
- [ ] Cross-domain reads (`/swing/...` returning accumulation data) do not exist.
