# 03 — Database

> SQLAlchemy 2.0 ORM. Alembic for migrations. SQLite (dev) → Postgres (prod). Same schema both.

---

## 1. Module layout

```
src/plutus/db/
├── __init__.py
├── session.py          # engine, sessionmaker, get_session()
├── models.py           # all ORM classes
└── init_db.py          # create_all() for tests; Alembic owns prod schema

migrations/
└── versions/
```

---

## 2. Tables (grouped by domain)

### 2.1 Shared

```python
class Universe(Base):
    """Point-in-time universe (A17). One row per (symbol, as_of_date)."""
    __tablename__ = "universe"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    as_of_date: Mapped[date] = mapped_column(index=True)
    median_traded_value_inr: Mapped[Decimal]
    free_float_mcap_inr: Mapped[Decimal | None]
    sector: Mapped[str | None]
    is_fno_listed: Mapped[bool] = mapped_column(default=False)
    in_universe: Mapped[bool]
    __table_args__ = (UniqueConstraint("symbol", "as_of_date"),)

class RegimeSnapshot(Base):
    """Daily regime snapshot."""
    __tablename__ = "regime_snapshot"
    as_of_date: Mapped[date] = mapped_column(primary_key=True)
    label: Mapped[Literal["BULL", "BEAR", "SIDEWAYS"]]
    nifty_close: Mapped[Decimal]
    pct_above_50dma: Mapped[float]
    pct_above_200dma: Mapped[float]
    advance_decline: Mapped[float]
    india_vix: Mapped[float]
    fii_flow_inr: Mapped[Decimal]
    dii_flow_inr: Mapped[Decimal]
    breadth_confirmed_flip: Mapped[bool] = mapped_column(default=False)

class CostModelRun(Base):
    """Audit of cost params used per backtest/live run."""
    __tablename__ = "cost_model_run"
    run_id: Mapped[str] = mapped_column(primary_key=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)  # all cost settings, frozen
    created_at: Mapped[datetime]

class BundleStatPerRegime(Base):
    """B14. Walk-forward OOS shrunk Sharpe per (bundle, regime, as_of_date)."""
    __tablename__ = "bundle_stat_per_regime"
    id: Mapped[int] = mapped_column(primary_key=True)
    bundle: Mapped[str] = mapped_column(index=True)
    regime: Mapped[str] = mapped_column(index=True)
    as_of_date: Mapped[date] = mapped_column(index=True)
    oos_sharpe_shrunk: Mapped[float]
    oos_expectancy_R: Mapped[float]
    n_trades: Mapped[int]
    ci_low: Mapped[float]
    ci_high: Mapped[float]
    __table_args__ = (UniqueConstraint("bundle", "regime", "as_of_date"),)

class CalibrationRow(Base):
    """A14. SPRT/CI-aware calibration per (bucket, regime)."""
    __tablename__ = "calibration_row"
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket: Mapped[str] = mapped_column(index=True)   # e.g. "trend_score_70_75"
    regime: Mapped[str] = mapped_column(index=True)
    n_closed: Mapped[int]
    win_rate: Mapped[float]
    expectancy_R: Mapped[float]
    ci_low_R: Mapped[float]
    ci_high_R: Mapped[float]
    sprt_state: Mapped[Literal["accept_H0", "accept_H1", "continue"]]
    last_updated: Mapped[datetime]
    confidence_band: Mapped[Literal["low", "medium", "high"]]
```

### 2.2 Swing

```python
class SwingSignal(Base):
    __tablename__ = "swing_signal"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(index=True)
    bundle: Mapped[str]
    score: Mapped[int]
    label: Mapped[Literal["BUY", "BUY_WATCH", "WATCH", "HOLD", "AVOID"]]
    entry: Mapped[Decimal]
    stop_loss: Mapped[Decimal]
    target_1: Mapped[Decimal]
    target_2: Mapped[Decimal]
    expectancy_R: Mapped[float]
    drawn_rr: Mapped[float]
    regime_at_signal: Mapped[str]
    pillar_breakdown_json: Mapped[dict] = mapped_column(JSON)
    counterfactual_text: Mapped[str | None]
    created_at: Mapped[datetime]

class SwingTrade(Base):
    __tablename__ = "swing_trade"
    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("swing_signal.id"))
    symbol: Mapped[str] = mapped_column(index=True)
    bundle: Mapped[str]
    state: Mapped[Literal["OPEN", "T1_HIT", "CLOSED_WIN", "CLOSED_LOSS", "SCRATCHED", "EXPIRED"]]
    opened_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    qty: Mapped[int]
    risk_R: Mapped[float]
    exit_reason: Mapped[str | None]
    realized_R: Mapped[float | None]
    mfe_R: Mapped[float | None]
    mae_R: Mapped[float | None]

class Fill(Base):
    """Both mock (backtest/paper) and real (user-logged) fills."""
    __tablename__ = "fill"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("swing_trade.id"))
    kind: Mapped[Literal["MOCK", "REAL"]]
    side: Mapped[Literal["BUY", "SELL"]]
    qty: Mapped[int]
    price: Mapped[Decimal]
    cost_inr: Mapped[Decimal]
    slippage_bps: Mapped[float | None]
    filled_at: Mapped[datetime]
```

### 2.3 Accumulation

```python
class AccumulationCandidate(Base):
    __tablename__ = "accumulation_candidate"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(index=True)
    score: Mapped[int]
    rs_30: Mapped[float]
    rs_90: Mapped[float]
    rs_180: Mapped[float]
    cagr_eps_3y: Mapped[float | None]
    valuation_pillar_pct: Mapped[float]
    thesis_text: Mapped[str]
    hard_avoid_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]

class AccumulationPosition(Base):
    __tablename__ = "accumulation_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(unique=True, index=True)
    state: Mapped[Literal["BUILDING", "FULL", "PAUSED", "EXITED", "CONVERTED_TO_SWING"]]
    avg_cost: Mapped[Decimal]
    qty_total: Mapped[int]
    opened_at: Mapped[datetime]
    last_thesis_check_at: Mapped[datetime]

class Tranche(Base):
    __tablename__ = "tranche"
    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("accumulation_position.id"))
    seq: Mapped[int]                          # 1..5
    atr_normalized_trigger_pct: Mapped[float] # A13 — not fixed -8/-15
    filled_at_price: Mapped[Decimal | None]
    filled_at: Mapped[datetime | None]
    thesis_revalidated: Mapped[bool] = mapped_column(default=False)
```

### 2.4 Reports

```python
class WeeklyPostmortem(Base):
    __tablename__ = "weekly_postmortem"
    week_ending: Mapped[date] = mapped_column(primary_key=True)
    swing_return_pct: Mapped[float]
    nifty_return_pct: Mapped[float]
    regime_switched_return_pct: Mapped[float]
    random_baseline_return_pct: Mapped[float]
    n_swing_trades_closed: Mapped[int]
    drawdown_pct: Mapped[float]
    report_md_path: Mapped[str]

class AlertCooldown(Base):
    """A16. Per-stock cooldown rows, separate keys for SL vs warning."""
    __tablename__ = "alert_cooldown"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(index=True)
    kind: Mapped[Literal["SL_BREACH", "SL_WARNING", "T1_HIT", "NO_PROGRESS"]]
    last_fired_at: Mapped[datetime]
```

---

## 3. Migrations (Alembic)

- One initial migration `0001_baseline.py` creates the full schema above.
- Subsequent additions get their own migration; never edit `0001`.
- Migrations live in `migrations/versions/`; configured to autogenerate from `models.py`.
- CI runs `alembic upgrade head` against a temp SQLite to verify migrations apply cleanly from zero.

---

## 4. `session.py`

```python
_engine = None

def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_url, future=True)
    return _engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=...)

@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
```

No global session. Every consumer takes a `Session` argument or uses `session_scope()`.

---

## 5. Tests (`tests/db/`)

| Test file | Cases |
|---|---|
| `test_models_universe.py` | Unique `(symbol, as_of_date)`. PIT round-trip on three dates. Reject negative `median_traded_value_inr`. |
| `test_models_regime.py` | Label enum constraint. `breadth_confirmed_flip=True` only if regime differs from yesterday. |
| `test_models_swing_signal.py` | All NOT-NULL constraints. `expectancy_R` cannot be set without `drawn_rr`. Round-trip JSON pillars. |
| `test_models_swing_trade.py` | State enum. Closing a trade requires `closed_at` and `realized_R`. |
| `test_models_fill.py` | Both `MOCK` and `REAL` accepted. Mock+real for same trade coexist (B10). |
| `test_models_accumulation_position.py` | `qty_total` non-negative. `avg_cost` recomputes on tranche insert (via helper, not trigger). |
| `test_models_tranche.py` | `seq` 1..5 ordered per position. Cannot fill a tranche without prior tranche filled. |
| `test_models_calibration_row.py` | CI ordering: `ci_low_R <= expectancy_R <= ci_high_R`. SPRT state enum. |
| `test_models_bundle_stat_per_regime.py` | Unique `(bundle, regime, as_of_date)`. Shrunk Sharpe in `[-3, 3]`. |
| `test_models_alert_cooldown.py` | Separate cooldown rows per kind (A16). Fetching `SL_WARNING` does not affect `SL_BREACH`. |
| `test_session_scope.py` | Exception inside `with session_scope()` rolls back; clean commit otherwise. |
| `test_migrations_apply_from_zero.py` | Alembic upgrade from empty DB to head succeeds. |
| `test_migrations_downgrade_one.py` | Each migration's `downgrade()` reverses cleanly. |

---

## Acceptance criteria

- [ ] Every table in §2 exists in `models.py`.
- [ ] Every test in §5 passes against SQLite.
- [ ] Same suite passes against a Postgres test container in CI.
- [ ] `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` clean.
- [ ] No raw SQL outside `db/`.
