# 04 — Accumulation domain (new)

## Goal

Add the second domain — accumulation mode — at `src/plutus/accumulation/`. This is patient-capital screening for bear and sideways markets. It scores Nifty 100 stocks on fundamentals, relative strength, and institutional flow. It does not place trades; it surfaces candidates, tracks user-logged tranches, and fires alerts.

## Public contract

```
plutus.accumulation
    ├── scoring.py
    │     compute_accumulation_score(...) -> (AccumScoreBreakdown, AccumClassification)
    │     AccumScoreBreakdown               (dataclass)
    │     AccumClassification               (Enum: STRONG_BUY | BUY | WATCH | AVOID)
    │     fundamental_pillar(...)           (float 0–100)
    │     relative_strength_pillar(...)     (float 0–100)
    │     institutional_flow_pillar(...)    (float 0–100)
    │
    ├── candidates.py
    │     screen_accumulation_universe(db, run_date) -> AccumulationRun
    │     rank_candidates(run_id) -> list[AccumulationCandidate]
    │
    ├── tranches.py
    │     create_position(db, portfolio_id, symbol, t1_price, qty, entry_date) -> AccumulationPosition
    │     add_tranche(db, position_id, tranche_num, price, qty, entry_date, triggered_by) -> AccumulationTranche
    │     recompute_avg_cost(position) -> None
    │     suggest_trigger_prices(t1_price) -> dict
    │
    ├── pipeline.py
    │     run_weekly_accumulation(db, run_date) -> AccumulationRun
    │
    └── triggers.py
          check_accumulation_positions(db, channels) -> int   (registered checker)
          on_regime_change(prev_trend, new_trend) -> None    (regime subscriber)
```

## Data sources

Reused (no new fetches needed):

| Source | Function | Purpose |
|---|---|---|
| OHLCV | `plutus.core.load_ohlcv(symbol)` | 30-day return calc for relative strength |
| Regime | `plutus.core.get_nifty_regime()` | Compute Nifty 30-day return baseline |
| Sector | `plutus.core.get_sector(symbol)` | Group stocks for sector-relative valuation |
| FII/DII | `plutus.core.get_fii_dii_flow()` | Market-wide institutional flow |
| MF | `plutus.core.get_mf_signal(symbol)` | Per-stock accumulation verdict |

New:

| Source | Function | Module |
|---|---|---|
| yfinance fundamentals | `get_fundamentals(symbol)` | `core/data/fundamentals.py` (see 04.1) |
| Sector median P/E | `get_sector_median_pe(universe, sector)` | `core/data/fundamentals.py` |

## Tasks

### 04.1 — New module: `core/data/fundamentals.py`

This sits in `core/data/` because both domains may eventually use it (swing might want P/E in the future). Today only accumulation does.

```python
# src/plutus/core/data/fundamentals.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
import yfinance as yf

from plutus.core.config import settings

CACHE_DIR = Path(settings.FUNDAMENTALS_CACHE_DIR)
CACHE_TTL = timedelta(days=7)

@dataclass(frozen=True)
class Fundamentals:
    pe: float | None
    de: float | None
    eps_growth: float | None
    source: str               # 'yfinance' | 'cache' | 'none'
    fetched_at: datetime

def get_fundamentals(symbol: str) -> Fundamentals:
    """Return Fundamentals for an NSE symbol.

    Order of resolution:
        1. Disk cache (7-day TTL)
        2. yfinance (symbol + '.NS')
        3. Empty (all None, source='none')

    Network errors are swallowed; the caller treats `source='none'` as "data unavailable"
    rather than as a hard failure.
    """

def get_sector_median_pe(universe: list[str], sector: str) -> float | None:
    """Median trailing P/E across `universe` stocks classified into `sector`.

    Stocks without P/E or sector data are skipped. Returns None if fewer than 3 valid stocks.
    """
```

Add to `core/config.py`:

```python
FUNDAMENTALS_CACHE_DIR: str = "data/fundamentals_cache"
```

Tests:

```python
# tests/core/data/test_fundamentals.py
def test_get_fundamentals_caches(tmp_path, monkeypatch, mock_yfinance):
    monkeypatch.setattr(fundamentals, "CACHE_DIR", tmp_path)
    mock_yfinance.set("HDFCBANK.NS", {"trailingPE": 18.2, "debtToEquity": 0.4, "earningsQuarterlyGrowth": 0.12})
    f1 = get_fundamentals("HDFCBANK")
    assert f1.pe == 18.2 and f1.de == 0.4 and f1.eps_growth == 0.12
    assert f1.source == "yfinance"
    mock_yfinance.fail_next()  # next call must NOT hit network
    f2 = get_fundamentals("HDFCBANK")
    assert f2.source == "cache"
    assert f2.pe == 18.2

def test_get_fundamentals_yfinance_failure_returns_none(monkeypatch, mock_yfinance):
    mock_yfinance.always_fail()
    f = get_fundamentals("UNKNOWN")
    assert f.pe is None and f.de is None and f.eps_growth is None
    assert f.source == "none"

def test_get_fundamentals_partial_data(monkeypatch, mock_yfinance):
    mock_yfinance.set("INFY.NS", {"trailingPE": 22.0})  # missing de, growth
    f = get_fundamentals("INFY")
    assert f.pe == 22.0 and f.de is None and f.eps_growth is None
    assert f.source == "yfinance"

def test_sector_median_pe_skips_invalid(monkeypatch, mock_yfinance):
    mock_yfinance.set("A.NS", {"trailingPE": 10.0})
    mock_yfinance.set("B.NS", {"trailingPE": 20.0})
    mock_yfinance.set("C.NS", {"trailingPE": 30.0})
    mock_yfinance.set("D.NS", {})  # no PE — skipped
    universe = ["A", "B", "C", "D"]
    monkeypatch.setattr(fundamentals, "get_sector", lambda s: "IT")
    assert get_sector_median_pe(universe, "IT") == 20.0

def test_sector_median_pe_returns_none_under_3_stocks(monkeypatch, mock_yfinance):
    mock_yfinance.set("A.NS", {"trailingPE": 10.0})
    mock_yfinance.set("B.NS", {"trailingPE": 20.0})
    assert get_sector_median_pe(["A", "B"], "IT") is None
```

Acceptance: 5 tests pass. The `mock_yfinance` fixture spec is in `06-testing-strategy.md`.

### 04.2 — `accumulation/scoring.py`

Mirror the structure of `swing/scoring.py:1-414`. Pure functions, no LLM.

```python
# src/plutus/accumulation/scoring.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd

class AccumClassification(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY        = "BUY"
    WATCH      = "WATCH"
    AVOID      = "AVOID"

PILLAR_WEIGHTS: dict[str, float] = {
    "fundamental":        0.40,
    "relative_strength":  0.30,
    "institutional_flow": 0.30,
}

STRONG_BUY_THRESHOLD = 75
BUY_THRESHOLD        = 60
WATCH_THRESHOLD      = 45

@dataclass(frozen=True)
class AccumScoreBreakdown:
    fundamental:        float
    relative_strength:  float
    institutional_flow: float
    hard_avoid_reasons: tuple = field(default_factory=tuple)

    @property
    def composite(self) -> int:
        return round(sum(getattr(self, k) * w for k, w in PILLAR_WEIGHTS.items()))


def fundamental_pillar(pe: float | None, de: float | None,
                       eps_growth: float | None, sector_median_pe: float | None) -> tuple[float, list[str]]:
    """Returns (score, hard_avoid_reasons).

    Sub-components:
        - Valuation (50%): PE vs sector median.
            PE < 0.7 × sector_median  → 100
            PE ≤ 1.0 × sector_median  → 70
            PE > 1.5 × sector_median  → 0
        - Debt (25%): D/E.
            D/E < 1.0  → 100
            D/E ≤ 2.0  → 60
            D/E > 3.0  → 0   (hard avoid: 'debt_load')
        - Growth (25%): EPS growth (YoY).
            growth > 0.20  → 100
            growth > 0.10  → 70
            growth > 0.0   → 50
            growth < -0.20 → 0  (hard avoid: 'earnings_collapse')

    Missing inputs degrade gracefully: each missing sub-component contributes 50 (neutral).
    Hard avoids still fire on D/E > 3 or growth < -20% only when the value is present.
    """

def relative_strength_pillar(df: pd.DataFrame, nifty_30d_return: float) -> float:
    """30-day stock return minus Nifty 30-day return.

    diff_pct = stock_30d_pct - nifty_30d_pct
    diff ≥ +5%  → 100
    diff ≥  0%  → 70
    diff ≥ -3%  → 50
    diff ≥ -7%  → 25
    diff < -7%  → 0

    Empty/short df returns 50.
    """

def institutional_flow_pillar(fii: dict, dii: dict, mf: dict) -> float:
    """Reuse the swing pillar formula exactly — same shape, same inputs."""
    from plutus.swing.scoring import smart_money_pillar
    return smart_money_pillar(fii, dii, mf)

def _accum_classify(breakdown: AccumScoreBreakdown) -> AccumClassification:
    if breakdown.hard_avoid_reasons:
        return AccumClassification.AVOID
    c = breakdown.composite
    if c >= STRONG_BUY_THRESHOLD: return AccumClassification.STRONG_BUY
    if c >= BUY_THRESHOLD:        return AccumClassification.BUY
    if c >= WATCH_THRESHOLD:      return AccumClassification.WATCH
    return AccumClassification.AVOID

def compute_accumulation_score(
    symbol: str,
    indicator_df: pd.DataFrame,
    fundamentals: Fundamentals,
    sector_median_pe: float | None,
    nifty_30d_return: float,
    fii: dict, dii: dict, mf: dict,
) -> tuple[AccumScoreBreakdown, AccumClassification]:
    fund_score, hard = fundamental_pillar(
        pe=fundamentals.pe, de=fundamentals.de,
        eps_growth=fundamentals.eps_growth,
        sector_median_pe=sector_median_pe,
    )
    rs   = relative_strength_pillar(indicator_df, nifty_30d_return)
    inst = institutional_flow_pillar(fii, dii, mf)
    breakdown = AccumScoreBreakdown(
        fundamental=fund_score, relative_strength=rs, institutional_flow=inst,
        hard_avoid_reasons=tuple(hard),
    )
    return breakdown, _accum_classify(breakdown)
```

**Cross-domain reuse note:** the `from plutus.swing.scoring import smart_money_pillar` import inside `institutional_flow_pillar` is the one allowed exception to domain isolation rule C. It is a pure function with identical inputs and identical semantics — copy-pasting would create maintenance drift. If you find more reuse opportunities of this kind, lift `smart_money_pillar` to `core/` instead of adding more cross-domain imports.

Tests (TDD — write these first, in this order):

```python
# tests/accumulation/test_scoring.py

class TestFundamentalPillar:
    def test_cheap_low_debt_strong_growth_max_score(self):
        s, h = fundamental_pillar(pe=12.0, de=0.3, eps_growth=0.25, sector_median_pe=20.0)
        assert s == 100.0 and h == []

    def test_expensive_no_growth_low_score(self):
        s, h = fundamental_pillar(pe=40.0, de=2.5, eps_growth=0.0, sector_median_pe=20.0)
        assert s < 30 and h == []

    def test_debt_over_3_hard_avoids(self):
        _, h = fundamental_pillar(pe=15.0, de=4.0, eps_growth=0.1, sector_median_pe=20.0)
        assert "debt_load" in h

    def test_collapsing_earnings_hard_avoids(self):
        _, h = fundamental_pillar(pe=15.0, de=1.0, eps_growth=-0.30, sector_median_pe=20.0)
        assert "earnings_collapse" in h

    def test_missing_fields_neutral_contribution(self):
        # All missing → 50 (pure neutrality)
        s, h = fundamental_pillar(pe=None, de=None, eps_growth=None, sector_median_pe=None)
        assert s == 50.0 and h == []

    def test_missing_sector_median_uses_neutral_valuation(self):
        s, h = fundamental_pillar(pe=15.0, de=0.5, eps_growth=0.15, sector_median_pe=None)
        # Valuation = 50, Debt = 100, Growth = 70 → 0.5*50 + 0.25*100 + 0.25*70 = 67.5
        assert s == pytest.approx(67.5, abs=0.5)

class TestRelativeStrengthPillar:
    def test_outperforming_by_5pct_max(self, df_with_returns):
        df = df_with_returns(stock_30d=0.10)
        assert relative_strength_pillar(df, nifty_30d_return=0.05) == 100.0
    def test_inline_with_nifty(self, df_with_returns):
        df = df_with_returns(stock_30d=0.05)
        assert relative_strength_pillar(df, nifty_30d_return=0.05) == 70.0
    def test_slightly_underperforming(self, df_with_returns):
        df = df_with_returns(stock_30d=0.02)
        # diff = -3pct → 50
        assert relative_strength_pillar(df, nifty_30d_return=0.05) == 50.0
    def test_severely_underperforming(self, df_with_returns):
        df = df_with_returns(stock_30d=-0.05)
        # diff = -10pct → 0
        assert relative_strength_pillar(df, nifty_30d_return=0.05) == 0.0
    def test_empty_df_returns_neutral(self):
        assert relative_strength_pillar(pd.DataFrame(), nifty_30d_return=0.0) == 50.0

class TestInstitutionalFlowPillar:
    def test_matches_swing_smart_money_pillar(self):
        fii = {"fii_signal": "net_buyer"}; dii = {"dii_signal": "net_buyer"}
        mf = {"verdict": "ACCUMULATING"}
        from plutus.swing.scoring import smart_money_pillar
        assert institutional_flow_pillar(fii, dii, mf) == smart_money_pillar(fii, dii, mf)

class TestClassify:
    def _make(self, **kw): return AccumScoreBreakdown(**{**dict(fundamental=80, relative_strength=80, institutional_flow=80), **kw})
    def test_strong_buy_at_75(self):
        b = self._make(fundamental=90, relative_strength=80, institutional_flow=70)
        assert _accum_classify(b) == AccumClassification.STRONG_BUY  # composite 80
    def test_buy_at_60(self):
        b = self._make(fundamental=60, relative_strength=60, institutional_flow=60)
        assert _accum_classify(b) == AccumClassification.BUY
    def test_watch_at_45(self):
        b = self._make(fundamental=45, relative_strength=45, institutional_flow=45)
        assert _accum_classify(b) == AccumClassification.WATCH
    def test_avoid_below_45(self):
        b = self._make(fundamental=30, relative_strength=30, institutional_flow=30)
        assert _accum_classify(b) == AccumClassification.AVOID
    def test_hard_avoid_overrides_composite(self):
        b = self._make(hard_avoid_reasons=("debt_load",))
        assert _accum_classify(b) == AccumClassification.AVOID

class TestComputeAccumulationScore:
    def test_end_to_end_strong_buy(self, sample_df, sample_fundamentals_strong):
        breakdown, cls = compute_accumulation_score(
            symbol="HDFCBANK",
            indicator_df=sample_df,
            fundamentals=sample_fundamentals_strong,
            sector_median_pe=20.0,
            nifty_30d_return=-0.03,
            fii={"fii_signal": "net_buyer"},
            dii={"dii_signal": "net_buyer"},
            mf={"verdict": "ACCUMULATING"},
        )
        assert cls == AccumClassification.STRONG_BUY
        assert breakdown.composite >= 75
```

Acceptance: 23 tests pass. Composite scores never fall outside `[0, 100]`. Every breakdown surfaced by `compute_accumulation_score` round-trips to the same classification.

### 04.3 — DB schema migration

Create `src/plutus/core/db/migrations/012_phase9_accumulation.sql`:

```sql
CREATE TABLE IF NOT EXISTS accumulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date DATE NOT NULL,
    run_type VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    stocks_screened INTEGER NOT NULL,
    nifty_regime VARCHAR(12),
    params_version_id VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accumulation_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accumulation_run_id INTEGER NOT NULL REFERENCES accumulation_runs(id),
    symbol VARCHAR(20) NOT NULL,
    composite INTEGER NOT NULL,
    fundamental REAL NOT NULL,
    relative_strength REAL NOT NULL,
    institutional_flow REAL NOT NULL,
    classification VARCHAR(15) NOT NULL,
    pe REAL, de REAL, eps_growth REAL,
    sector VARCHAR(30),
    hard_avoid_reasons TEXT,            -- comma-separated, may be NULL
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_accum_candidates_run ON accumulation_candidates (accumulation_run_id);
CREATE INDEX IF NOT EXISTS idx_accum_candidates_sym ON accumulation_candidates (symbol);
CREATE INDEX IF NOT EXISTS idx_accum_candidates_cls ON accumulation_candidates (classification);

CREATE TABLE IF NOT EXISTS accumulation_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES mock_portfolios(id),
    symbol VARCHAR(20) NOT NULL,
    t1_entry_price REAL NOT NULL,
    t1_entry_date DATE NOT NULL,
    target_tranches INTEGER NOT NULL DEFAULT 3,
    avg_cost REAL NOT NULL,
    total_shares INTEGER NOT NULL,
    total_capital_used REAL NOT NULL,
    status VARCHAR(15) NOT NULL DEFAULT 'BUILDING',
    bull_ready_alerted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_accum_positions_portfolio ON accumulation_positions (portfolio_id);
CREATE INDEX IF NOT EXISTS idx_accum_positions_status ON accumulation_positions (status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_accum_positions_open_symbol
    ON accumulation_positions (portfolio_id, symbol)
    WHERE status IN ('BUILDING', 'COMPLETE');

CREATE TABLE IF NOT EXISTS accumulation_tranches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL REFERENCES accumulation_positions(id),
    tranche_num INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    shares INTEGER NOT NULL,
    entry_date DATE NOT NULL,
    triggered_by VARCHAR(20) DEFAULT 'manual',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (position_id, tranche_num)
);
CREATE INDEX IF NOT EXISTS idx_accum_tranches_pos ON accumulation_tranches (position_id);
```

`src/plutus/core/db/models/accumulation.py`:

```python
class AccumulationRun(Base):
    __tablename__ = "accumulation_runs"
    id = Column(Integer, primary_key=True)
    run_date = Column(Date, nullable=False)
    run_type = Column(String(20), default="scheduled")
    stocks_screened = Column(Integer, nullable=False)
    nifty_regime = Column(String(12))
    params_version_id = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    candidates = relationship("AccumulationCandidate", backref="run")

class AccumulationCandidate(Base):
    __tablename__ = "accumulation_candidates"
    id = Column(Integer, primary_key=True)
    accumulation_run_id = Column(Integer, ForeignKey("accumulation_runs.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    composite = Column(Integer, nullable=False)
    fundamental = Column(Float, nullable=False)
    relative_strength = Column(Float, nullable=False)
    institutional_flow = Column(Float, nullable=False)
    classification = Column(String(15), nullable=False)
    pe = Column(Float); de = Column(Float); eps_growth = Column(Float)
    sector = Column(String(30))
    hard_avoid_reasons = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

class AccumulationPosition(Base):
    __tablename__ = "accumulation_positions"
    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("mock_portfolios.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    t1_entry_price = Column(Float, nullable=False)
    t1_entry_date = Column(Date, nullable=False)
    target_tranches = Column(Integer, default=3)
    avg_cost = Column(Float, nullable=False)
    total_shares = Column(Integer, nullable=False)
    total_capital_used = Column(Float, nullable=False)
    status = Column(String(15), default="BUILDING")
    bull_ready_alerted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tranches = relationship("AccumulationTranche", backref="position",
                             order_by="AccumulationTranche.tranche_num")

class AccumulationTranche(Base):
    __tablename__ = "accumulation_tranches"
    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey("accumulation_positions.id"), nullable=False)
    tranche_num = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False)
    entry_date = Column(Date, nullable=False)
    triggered_by = Column(String(20), default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)
```

Re-export from `core/db/models/__init__.py`.

Tests:

```python
# tests/accumulation/test_models.py
def test_migration_applies_idempotent(in_memory_db):
    apply_migration("012_phase9_accumulation.sql", in_memory_db)
    apply_migration("012_phase9_accumulation.sql", in_memory_db)  # second time = no-op

def test_can_persist_run_and_candidates(in_memory_db):
    run = AccumulationRun(run_date=date(2026,6,7), stocks_screened=98, nifty_regime="BEAR")
    in_memory_db.add(run); in_memory_db.commit()
    c = AccumulationCandidate(
        accumulation_run_id=run.id, symbol="HDFCBANK", composite=78,
        fundamental=82.0, relative_strength=74.0, institutional_flow=70.0,
        classification="STRONG_BUY", pe=18.0, de=0.4, eps_growth=0.12, sector="BANK",
    )
    in_memory_db.add(c); in_memory_db.commit()
    assert run.candidates[0].symbol == "HDFCBANK"

def test_position_unique_open_per_symbol(in_memory_db, seeded_portfolio):
    pos1 = _make_position(portfolio_id=seeded_portfolio.id, symbol="HDFCBANK", status="BUILDING")
    in_memory_db.add(pos1); in_memory_db.commit()
    pos2 = _make_position(portfolio_id=seeded_portfolio.id, symbol="HDFCBANK", status="BUILDING")
    with pytest.raises(IntegrityError):
        in_memory_db.add(pos2); in_memory_db.commit()

def test_position_can_exit_and_recreate(in_memory_db, seeded_portfolio):
    pos1 = _make_position(...status="EXITED")
    in_memory_db.add(pos1); in_memory_db.commit()
    pos2 = _make_position(...status="BUILDING")
    in_memory_db.add(pos2); in_memory_db.commit()  # allowed because pos1 is EXITED

def test_tranche_unique_per_position(in_memory_db, seeded_position):
    t1a = AccumulationTranche(position_id=seeded_position.id, tranche_num=1, ...)
    t1b = AccumulationTranche(position_id=seeded_position.id, tranche_num=1, ...)
    in_memory_db.add_all([t1a, t1b])
    with pytest.raises(IntegrityError): in_memory_db.commit()
```

Acceptance: 5 tests pass.

### 04.4 — `accumulation/tranches.py`

```python
TRIGGERED_BY_MANUAL = "manual"
TRIGGERED_BY_T2_ALERT = "t2_alert"
TRIGGERED_BY_T3_ALERT = "t3_alert"

def suggest_trigger_prices(t1_price: float) -> dict:
    """Returns {'t2_trigger': float, 't3_trigger': float} using params from get_params().

    Defaults: T2 = -8% from T1, T3 = -15% from T1.
    """
    params = get_params()
    return {
        "t2_trigger": round(t1_price * (1 - params["t2_drop_pct"] / 100), 2),
        "t3_trigger": round(t1_price * (1 - params["t3_drop_pct"] / 100), 2),
    }

def create_position(db, portfolio_id: int, symbol: str,
                     t1_price: float, qty: int, entry_date: date) -> AccumulationPosition:
    """Open a new accumulation position with tranche 1 logged.

    Raises:
        ValueError: if an open position for (portfolio, symbol) already exists.
        BudgetExceededError: if total_capital_used across all open accum positions
            would exceed accumulation_budget_pct of initial_capital.
    """

def add_tranche(db, position_id: int, tranche_num: int,
                 price: float, qty: int, entry_date: date,
                 triggered_by: str = TRIGGERED_BY_MANUAL) -> AccumulationTranche:
    """Log a tranche (1, 2, or 3) on an existing position.

    On success:
        - Inserts AccumulationTranche row.
        - Recomputes parent position's avg_cost, total_shares, total_capital_used.
        - If tranche_num == position.target_tranches, sets status='COMPLETE'.

    Raises:
        ValueError: tranche_num out of range, tranche already logged, position not BUILDING.
        BudgetExceededError: budget cap would be breached.
    """

def recompute_avg_cost(position: AccumulationPosition) -> None:
    """Updates avg_cost, total_shares, total_capital_used on `position` from its tranches.

    Caller is responsible for committing.
    """
    total_qty = sum(t.shares for t in position.tranches)
    total_cap = sum(t.shares * t.entry_price for t in position.tranches)
    position.total_shares = total_qty
    position.total_capital_used = round(total_cap, 2)
    position.avg_cost = round(total_cap / total_qty, 2) if total_qty else 0.0
```

`BudgetExceededError` lives in `accumulation/__init__.py`.

Tests:

```python
# tests/accumulation/test_tranches.py

def test_suggest_trigger_prices_default():
    out = suggest_trigger_prices(t1_price=1000.0)
    assert out == {"t2_trigger": 920.0, "t3_trigger": 850.0}

def test_create_position_persists_t1_and_position(in_memory_db, seeded_portfolio):
    pos = create_position(in_memory_db, portfolio_id=seeded_portfolio.id,
                          symbol="HDFCBANK", t1_price=1600.0, qty=10, entry_date=date(2026,6,7))
    assert pos.id and pos.avg_cost == 1600.0 and pos.total_shares == 10
    assert len(pos.tranches) == 1
    assert pos.tranches[0].tranche_num == 1

def test_create_position_duplicate_open_raises(in_memory_db, seeded_portfolio):
    create_position(in_memory_db, ..., symbol="HDFCBANK", ...)
    with pytest.raises(ValueError, match="already exists"):
        create_position(in_memory_db, ..., symbol="HDFCBANK", ...)

def test_create_position_over_budget_raises(in_memory_db, seeded_portfolio, set_params):
    set_params({"initial_capital": 100_000, "accumulation_budget_pct": 40.0})
    with pytest.raises(BudgetExceededError):
        create_position(in_memory_db, ..., t1_price=10_000, qty=5)  # ₹50k > ₹40k

def test_add_tranche_updates_avg_cost(in_memory_db, seeded_position):
    # T1 at ₹1600, 10 shares — already seeded
    add_tranche(in_memory_db, position_id=seeded_position.id,
                 tranche_num=2, price=1480.0, qty=10, entry_date=date(2026,6,15))
    in_memory_db.refresh(seeded_position)
    assert seeded_position.total_shares == 20
    assert seeded_position.avg_cost == 1540.0
    assert seeded_position.total_capital_used == 30800.0

def test_add_tranche_3_marks_position_complete(in_memory_db, seeded_position_with_t1_t2):
    add_tranche(in_memory_db, position_id=seeded_position_with_t1_t2.id,
                 tranche_num=3, price=1360.0, qty=10, entry_date=date(2026,6,28))
    in_memory_db.refresh(seeded_position_with_t1_t2)
    assert seeded_position_with_t1_t2.status == "COMPLETE"

def test_add_tranche_duplicate_num_raises(in_memory_db, seeded_position):
    with pytest.raises(ValueError, match="tranche 1 already logged"):
        add_tranche(in_memory_db, position_id=seeded_position.id,
                     tranche_num=1, price=1700.0, qty=5, entry_date=date(2026,6,10))

def test_add_tranche_to_completed_position_raises(in_memory_db, completed_position):
    with pytest.raises(ValueError, match="position not BUILDING"):
        add_tranche(in_memory_db, ..., tranche_num=2, ...)
```

Acceptance: 8 tests pass.

### 04.5 — `accumulation/candidates.py`

```python
def screen_accumulation_universe(db, run_date: date) -> AccumulationRun:
    """Score every symbol in get_universe('accumulation'), persist results.

    Reuses cached OHLCV (from concurrent swing run if present) via load_ohlcv().
    Reuses FII/DII fetch by passing them once through the loop.
    Reuses regime snapshot (read from DB, written by swing run earlier in the day).

    Side effects:
        - Inserts 1 AccumulationRun row.
        - Inserts N AccumulationCandidate rows (one per screened symbol).
    """
    run = AccumulationRun(run_date=run_date, run_type="scheduled",
                          stocks_screened=0, nifty_regime=get_nifty_regime()["trend"])
    db.add(run); db.flush()
    universe = get_universe(kind="accumulation")
    nifty_30d = _nifty_30d_return(db)
    fii = get_fii_dii_flow()  # market-wide, fetched once
    dii = fii.copy()           # smart_money returns combined dict
    sector_pe_cache: dict[str, float | None] = {}
    rows = []
    for sym in universe:
        df = load_ohlcv(sym, persist_if_fetched=True)
        if df is None or df.empty: continue
        fundamentals = get_fundamentals(sym)
        sector = get_sector(sym) or "UNKNOWN"
        if sector not in sector_pe_cache:
            sector_pe_cache[sector] = get_sector_median_pe(universe, sector)
        mf = get_mf_signal(sym)
        breakdown, cls = compute_accumulation_score(
            symbol=sym, indicator_df=df, fundamentals=fundamentals,
            sector_median_pe=sector_pe_cache[sector],
            nifty_30d_return=nifty_30d,
            fii=fii, dii=dii, mf=mf,
        )
        rows.append(AccumulationCandidate(
            accumulation_run_id=run.id, symbol=sym,
            composite=breakdown.composite,
            fundamental=breakdown.fundamental,
            relative_strength=breakdown.relative_strength,
            institutional_flow=breakdown.institutional_flow,
            classification=cls.value,
            pe=fundamentals.pe, de=fundamentals.de, eps_growth=fundamentals.eps_growth,
            sector=sector,
            hard_avoid_reasons=",".join(breakdown.hard_avoid_reasons) or None,
        ))
    db.bulk_save_objects(rows)
    run.stocks_screened = len(rows)
    run.completed_at = datetime.utcnow()
    db.commit()
    return run

def rank_candidates(db, run_id: int, *, min_composite: int = 45) -> list[AccumulationCandidate]:
    return (
        db.query(AccumulationCandidate)
          .filter_by(accumulation_run_id=run_id)
          .filter(AccumulationCandidate.composite >= min_composite)
          .order_by(AccumulationCandidate.composite.desc())
          .all()
    )
```

Tests:

```python
# tests/accumulation/test_candidates.py
def test_screen_persists_one_run_n_candidates(in_memory_db, mock_data_layer):
    mock_data_layer.universe(["HDFCBANK", "TCS", "INFY"])
    mock_data_layer.fundamentals({
        "HDFCBANK": Fundamentals(pe=18, de=0.4, eps_growth=0.12, source="yfinance", fetched_at=now()),
        "TCS":      Fundamentals(pe=25, de=0.0, eps_growth=0.08, source="yfinance", fetched_at=now()),
        "INFY":     Fundamentals(pe=22, de=0.1, eps_growth=0.10, source="yfinance", fetched_at=now()),
    })
    run = screen_accumulation_universe(in_memory_db, date(2026,6,7))
    assert run.stocks_screened == 3
    assert len(run.candidates) == 3
    syms = {c.symbol for c in run.candidates}
    assert syms == {"HDFCBANK", "TCS", "INFY"}

def test_screen_skips_symbols_with_no_ohlcv(in_memory_db, mock_data_layer):
    mock_data_layer.universe(["HDFCBANK", "DELISTED"])
    mock_data_layer.no_ohlcv("DELISTED")
    run = screen_accumulation_universe(in_memory_db, date(2026,6,7))
    assert run.stocks_screened == 1

def test_rank_candidates_filters_by_min_composite(in_memory_db, seeded_run_with_mixed_scores):
    ranked = rank_candidates(in_memory_db, run_id=seeded_run_with_mixed_scores.id, min_composite=60)
    assert all(c.composite >= 60 for c in ranked)
    assert ranked == sorted(ranked, key=lambda c: -c.composite)
```

Acceptance: 3 tests pass.

### 04.6 — `accumulation/pipeline.py`

```python
async def run_weekly_accumulation(db, run_date: date) -> AccumulationRun:
    """Top-level Sunday accumulation pipeline.

    Order of operations:
        1. Confirm regime snapshot exists for today (written by swing pipeline earlier).
           If not, log a warning and skip — accumulation needs the regime context.
        2. Call screen_accumulation_universe(db, run_date).
        3. Write a postmortem Telegram message: "Accumulation run done — N candidates,
           top 3 STRONG_BUY, top 3 BUY, X stocks newly entered the screen this week."

    This function is the entry point the scheduler calls. Wired into main.py.
    """
```

Tests:

```python
# tests/accumulation/test_pipeline.py
@pytest.mark.asyncio
async def test_run_weekly_accumulation_creates_run(in_memory_db, mock_data_layer, regime_snapshot):
    regime_snapshot(in_memory_db, trend="BEAR")
    mock_data_layer.universe(["HDFCBANK", "TCS"])
    mock_data_layer.fundamentals({...})
    run = await run_weekly_accumulation(in_memory_db, date(2026,6,7))
    assert run.run_type == "scheduled"
    assert run.stocks_screened == 2

@pytest.mark.asyncio
async def test_run_weekly_accumulation_warns_without_regime(in_memory_db, mock_data_layer, caplog):
    mock_data_layer.universe(["HDFCBANK"])
    result = await run_weekly_accumulation(in_memory_db, date(2026,6,7))
    assert result is None
    assert "regime snapshot missing" in caplog.text
```

Acceptance: 2 tests pass.

### 04.7 — `accumulation/triggers.py`

```python
from plutus.core.alerts.monitor import register_position_checker
from plutus.core.data.regime import subscribe_regime_change

def check_accumulation_positions(db, channels) -> int:
    """For each open AccumulationPosition (status='BUILDING'):
       fetch LTP, compare against suggest_trigger_prices(t1).
       Fire TRANCHE2_TRIGGER / TRANCHE3_TRIGGER (with 1-h cooldown)."""

def on_regime_change(prev_trend: str, new_trend: str) -> None:
    """Subscriber: when BEAR/SIDEWAYS → BULL, re-score all open accum positions
       under the swing rubric. Fire one BULL_READY alert per position whose
       composite now ≥ swing BUY threshold, then set bull_ready_alerted_at."""

register_position_checker(check_accumulation_positions)
subscribe_regime_change(on_regime_change)
```

Tests:

```python
# tests/accumulation/test_triggers.py
def test_tranche2_fires_when_ltp_below_trigger(in_memory_db, seeded_position, monkeypatch, fake_channel):
    # seeded_position: T1=1000, T2 trigger = 920
    monkeypatch.setattr(triggers, "fetch_live_price", lambda s: 915)
    n = check_accumulation_positions(in_memory_db, [fake_channel])
    assert n == 1
    assert "T2 trigger hit" in fake_channel.sent[0]

def test_tranche2_dedup_within_hour(in_memory_db, seeded_position, monkeypatch, fake_channel):
    monkeypatch.setattr(triggers, "fetch_live_price", lambda s: 915)
    check_accumulation_positions(in_memory_db, [fake_channel])
    n = check_accumulation_positions(in_memory_db, [fake_channel])
    assert n == 0

def test_tranche2_does_not_fire_when_above_trigger(in_memory_db, seeded_position, monkeypatch, fake_channel):
    monkeypatch.setattr(triggers, "fetch_live_price", lambda s: 950)  # > 920
    n = check_accumulation_positions(in_memory_db, [fake_channel])
    assert n == 0

def test_tranche3_fires_when_ltp_below_t3(in_memory_db, seeded_position_with_t2, monkeypatch, fake_channel):
    monkeypatch.setattr(triggers, "fetch_live_price", lambda s: 845)
    n = check_accumulation_positions(in_memory_db, [fake_channel])
    assert n == 1
    assert "T3 trigger hit" in fake_channel.sent[0]

def test_completed_positions_no_alert(in_memory_db, completed_position, monkeypatch, fake_channel):
    monkeypatch.setattr(triggers, "fetch_live_price", lambda s: 500)  # well below any trigger
    n = check_accumulation_positions(in_memory_db, [fake_channel])
    assert n == 0

def test_on_regime_change_bear_to_bull_fires_bull_ready(in_memory_db, seeded_position_high_score, fake_channel, monkeypatch):
    monkeypatch.setattr(triggers, "_rescore_for_swing", lambda pos: 78)  # > swing BUY threshold (70)
    on_regime_change("BEAR", "BULL")
    in_memory_db.refresh(seeded_position_high_score)
    assert seeded_position_high_score.bull_ready_alerted_at is not None

def test_on_regime_change_does_not_refire(in_memory_db, alerted_position, fake_channel):
    on_regime_change("BEAR", "BULL")  # bull_ready_alerted_at already set
    # No new alerts sent
```

Acceptance: 7 tests pass.

### 04.8 — `accumulation` public surface + main.py wiring

`src/plutus/accumulation/__init__.py`:

```python
from plutus.accumulation.scoring import (
    compute_accumulation_score,
    AccumScoreBreakdown,
    AccumClassification,
    PILLAR_WEIGHTS,
    STRONG_BUY_THRESHOLD, BUY_THRESHOLD, WATCH_THRESHOLD,
)
from plutus.accumulation.tranches import (
    create_position,
    add_tranche,
    suggest_trigger_prices,
    BudgetExceededError,
)
from plutus.accumulation.candidates import screen_accumulation_universe, rank_candidates
from plutus.accumulation.pipeline import run_weekly_accumulation
from plutus.accumulation.triggers import (
    check_accumulation_positions,
    on_regime_change,
)

import plutus.accumulation.triggers  # noqa: F401  (registers checker + subscriber on import)
```

In `main.py`, after `run_weekly_swing(...)` returns, add:

```python
import plutus.accumulation  # ensure registrations
from plutus.accumulation import run_weekly_accumulation
...
swing_run = await run_weekly_swing(db, run_date)
if settings.ACCUMULATION_ENABLED:
    await run_weekly_accumulation(db, run_date)
```

`settings.ACCUMULATION_ENABLED` defaults to `True`. Add to `core/config.py`.

Acceptance: `pytest tests/accumulation/ -q` passes (37 tests across this phase). `python main.py --health-check` succeeds.

### 04.9 — Trading params extension

In `core/config_params.py:PARAM_DEFAULTS`, add:

```python
"swing_budget_pct":           {"value": 40.0, "type": "float", "min": 0.0,   "max": 80.0,  "label": "Swing budget % of capital"},
"accumulation_budget_pct":    {"value": 40.0, "type": "float", "min": 0.0,   "max": 80.0,  "label": "Accumulation budget % of capital"},
"cash_reserve_pct":           {"value": 20.0, "type": "float", "min": 10.0,  "max": 100.0, "label": "Cash reserve % (floor 10%)"},
"tranches_per_candidate":     {"value": 3,    "type": "int",   "min": 2,     "max": 5,     "label": "Tranches per accumulation stock"},
"t2_drop_pct":                {"value": 8.0,  "type": "float", "min": 3.0,   "max": 20.0,  "label": "T2 trigger: % below T1"},
"t3_drop_pct":                {"value": 15.0, "type": "float", "min": 5.0,   "max": 30.0,  "label": "T3 trigger: % below T1"},
"accumulation_min_composite": {"value": 45,   "type": "int",   "min": 30,    "max": 75,    "label": "Min composite to surface candidate"},
```

Invariant validator:

```python
def validate_param_invariants(params: dict) -> None:
    total = params["swing_budget_pct"] + params["accumulation_budget_pct"] + params["cash_reserve_pct"]
    if total > 100:
        raise ValueError(f"Allocation sum {total:.1f}% exceeds 100%")
    if params["cash_reserve_pct"] < 10:
        raise ValueError("Cash reserve below 10% floor")
```

Hook it into `set_param()` so any update calls `validate_param_invariants(updated_params)` before commit.

Tests:

```python
# tests/core/test_config_params.py (extend)
def test_invariant_rejects_over_100(in_memory_db):
    set_param("swing_budget_pct", 50.0, updated_by="test")
    with pytest.raises(ValueError, match="exceeds 100"):
        set_param("accumulation_budget_pct", 60.0, updated_by="test")  # 50+60+20 = 130

def test_invariant_rejects_cash_below_floor(in_memory_db):
    with pytest.raises(ValueError, match="below 10% floor"):
        set_param("cash_reserve_pct", 5.0, updated_by="test")

def test_accumulation_params_have_defaults():
    p = get_params()
    assert p["t2_drop_pct"] == 8.0
    assert p["t3_drop_pct"] == 15.0
    assert p["accumulation_min_composite"] == 45
```

Acceptance: 3 tests pass.

## Verification gate for phase 04

- [ ] `pytest tests/accumulation/ -q` → 40+ tests passing (sum of all assertions in 04.1–04.9).
- [ ] Migration applies on fresh DB; applies again as no-op.
- [ ] `from plutus.accumulation import *` resolves the documented public surface (`compute_accumulation_score`, `AccumScoreBreakdown`, `create_position`, `add_tranche`, `screen_accumulation_universe`, `run_weekly_accumulation`).
- [ ] `python -c "import plutus.accumulation; from plutus.core.alerts.monitor import _REGISTERED_CHECKERS; print([f.__name__ for f in _REGISTERED_CHECKERS])"` includes both `check_swing_positions` and `check_accumulation_positions`.
- [ ] `python main.py --health-check` exits 0; the log line "accumulation pipeline enabled" appears with the default settings.
- [ ] Domain isolation: `grep -rn "from plutus.accumulation" src/plutus/swing/` returns 0 lines.
- [ ] Domain isolation exception: the only `plutus.swing` import inside `src/plutus/accumulation/` is `smart_money_pillar` in `accumulation/scoring.py:institutional_flow_pillar()`.

Do not start phase 05 until every box is checked.
