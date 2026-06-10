# Phase 3a — Nifty Regime + Sector Index Data

```yaml
phase_id: phase_3a
status: pending
depends_on: []
blocks: [phase_1, phase_2, dashboard]
estimated_effort: 2 days
test_framework: pytest
```

## Goal

The Regime pillar (Phase 1) and the regime gates inside hardened bundles (Phase 2) need a deterministic `get_nifty_regime()` returning `{trend: BULL|BEAR|SIDEWAYS, slope, distance_from_ema50_pct}` and a `get_sector_strength()` returning RS of each sector index vs Nifty. Today, `weekly_runs.market_regime` is stored but its source is unclear. This phase pins it.

## Acceptance criteria

- [ ] `get_nifty_regime()` returns a deterministic dict given the same date+OHLCV
- [ ] `get_sector_strength()` returns a dict of 13 sector indices ranked by 30-day RS vs Nifty
- [ ] Both cached weekly (re-fetch on Sunday job)
- [ ] Persisted to `market_regime_snapshots` table on every weekly run
- [ ] No yfinance/jugaad fetch on hot path — all reads from cache during analysis

## Prerequisites

None.

## Task list

### TASK-3a.1 — Schema: `market_regime_snapshots` table

```yaml
parallelizable: no
parallel_group: null
reason: All other tasks persist to this table.
estimated_effort: 30min
```

**Test first**:
```python
# tests/test_regime/test_persistence.py
def test_market_regime_snapshot_persists(db_session):
    from plutus.db.models import MarketRegimeSnapshot
    snap = MarketRegimeSnapshot(
        snapshot_date=date(2026, 6, 1), nifty_trend="BULL", nifty_slope=0.45,
        distance_from_ema50_pct=3.5, sector_rs={"IT": 1.18, "BANK": 1.05},
    )
    db_session.add(snap); db_session.commit()
    row = db_session.query(MarketRegimeSnapshot).filter_by(snapshot_date=date(2026, 6, 1)).one()
    assert row.nifty_trend == "BULL"
    assert row.sector_rs["IT"] == pytest.approx(1.18)
```

**Files to modify**:
- `src/plutus/db/models.py` — add `MarketRegimeSnapshot` model with `sector_rs` as JSON column.
- `src/plutus/db/schema.sql` — DDL.
- `migrations/00X_regime_snapshots.sql` — `CREATE TABLE market_regime_snapshots ...`

**Acceptance**: migration runs; test green.

---

### TASK-3a.2 — Fetch indices via existing `fetch_ohlcv`

```yaml
parallelizable: no
parallel_group: null
reason: TASK-3a.3 depends on this.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_regime/test_index_fetch.py
def test_fetch_nifty_50(monkeypatch):
    # mock the jugaad/yfinance fallback to return a known df
    ...
    df = fetch_index_ohlcv("NIFTY50", days=90)
    assert df.attrs["bars_fetched"] >= 60
    assert "Close" in df.columns

def test_fetch_sector_index_nifty_bank(monkeypatch):
    df = fetch_index_ohlcv("NIFTY_BANK", days=90)
    assert df.attrs["bars_fetched"] >= 60

INDEX_SYMBOLS = ["NIFTY_50", "NIFTY_BANK", "NIFTY_IT", "NIFTY_AUTO", "NIFTY_FMCG",
                 "NIFTY_PHARMA", "NIFTY_METAL", "NIFTY_REALTY", "NIFTY_ENERGY",
                 "NIFTY_INFRA", "NIFTY_PSE", "NIFTY_MEDIA"]

@pytest.mark.parametrize("symbol", INDEX_SYMBOLS)
def test_all_indices_fetchable(symbol, monkeypatch):
    df = fetch_index_ohlcv(symbol, days=90)
    assert df.attrs["bars_fetched"] >= 60
```

**Files to create**:
- `src/plutus/data/regime.py` (new) — `fetch_index_ohlcv(symbol, days)` wrapping `fetch_ohlcv` with index-specific yfinance ticker symbols (`^NSEI`, `^CNXBANK`, etc.).

**Note**: yfinance index symbols are not the same as NSE plain names. Map them:
```python
INDEX_YF_MAP = {
    "NIFTY_50": "^NSEI", "NIFTY_BANK": "^NSEBANK", "NIFTY_IT": "^CNXIT", ...
}
```

**Acceptance**: parametrized test green for all 12 indices.

---

### TASK-3a.3 — `get_nifty_regime()`

```yaml
parallelizable: yes
parallel_group: 3A_compute
reason: Independent of TASK-3a.4.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_regime/test_compute.py
def test_bull_regime(synthetic_bull_nifty_df, monkeypatch):
    monkeypatch.setattr("plutus.data.regime.fetch_index_ohlcv",
                        lambda *a, **kw: synthetic_bull_nifty_df)
    r = get_nifty_regime()
    assert r["trend"] == "BULL"
    assert r["slope"] > 0
    assert r["distance_from_ema50_pct"] > 0

def test_bear_regime(synthetic_bear_nifty_df, monkeypatch):
    ...
    assert r["trend"] == "BEAR"

def test_sideways_regime(synthetic_flat_nifty_df, monkeypatch):
    ...
    assert r["trend"] == "SIDEWAYS"

def test_caches_result(monkeypatch):
    """Second call within a week should not refetch."""
    call_count = [0]
    def counter(*a, **kw):
        call_count[0] += 1
        return synthetic_bull_nifty_df()
    monkeypatch.setattr("plutus.data.regime.fetch_index_ohlcv", counter)
    get_nifty_regime(force=False)
    get_nifty_regime(force=False)
    assert call_count[0] == 1
```

**Files to modify**:
- `src/plutus/data/regime.py` — add `get_nifty_regime(force=False) -> dict`. Rules:
  - `trend = BULL` if `Close > EMA50 AND slope_5d > 0`
  - `trend = BEAR` if `Close < EMA50 AND slope_5d < 0`
  - Else `SIDEWAYS`
  - `slope` = (EMA50_today - EMA50_5d_ago) / EMA50_5d_ago
  - Cache to disk (joblib-style or simple JSON) with 7-day TTL.

**Acceptance**: four tests green.

---

### TASK-3a.4 — `get_sector_strength()`

```yaml
parallelizable: yes
parallel_group: 3A_compute
reason: Independent of TASK-3a.3.
estimated_effort: 2h
```

**Test first**:
```python
def test_sector_strength_returns_all_sectors(monkeypatch):
    ...
    rs = get_sector_strength()
    assert set(rs.keys()) >= {"IT", "BANK", "AUTO", "FMCG", "PHARMA", "METAL"}

def test_sector_outperformer_has_rs_above_1(monkeypatch):
    # mock IT as 20% up vs Nifty 5% up
    rs = get_sector_strength()
    assert rs["IT"] > 1.1

def test_sector_underperformer_has_rs_below_1(monkeypatch):
    rs = get_sector_strength()
    assert rs["METAL"] < 0.9
```

**Files to modify**:
- `src/plutus/data/regime.py` — add `get_sector_strength(force=False) -> dict[str, float]`. RS computation:
  ```python
  sector_30d_return = (close_today / close_30d_ago) - 1
  nifty_30d_return = (nifty_today / nifty_30d_ago) - 1
  rs[sector] = (1 + sector_30d_return) / (1 + nifty_30d_return)
  ```

**Acceptance**: three tests green.

---

### TASK-3a.5 — Wire into weekly pipeline

```yaml
parallelizable: no
parallel_group: null
reason: Sequential after compute functions.
estimated_effort: 1h
```

**Test first**:
```python
def test_weekly_pipeline_persists_regime_snapshot(db_session, monkeypatch):
    # Mock regime functions, run weekly pipeline (or its first stage)
    ...
    rows = db_session.query(MarketRegimeSnapshot).all()
    assert len(rows) == 1
    assert rows[0].snapshot_date == date.today()
```

**Files to modify**:
- `src/plutus/agents/graph.py` — new `regime_node` runs first, populates state.
- `main.py` (weekly_pipeline) — call `persist_regime_snapshot()` early.

**Acceptance**: test green; running `python -c "from main import weekly_pipeline; ..."` writes one regime snapshot row.

## Streamlit considerations

Phase 3a outputs feed the dashboard regime badge — UI implementation in `phase_dashboard.md`. Test seam: `at.session_state["nifty_regime"]` should be readable.

## Verification

```bash
pytest tests/test_regime/ -v
python -c "from plutus.data.regime import get_nifty_regime, get_sector_strength; print(get_nifty_regime()); print(get_sector_strength())"
```

## Done definition

- [ ] All 5 tasks complete
- [ ] All tests green
- [ ] Phase 1 (Regime pillar) and Phase 2 (regime gates) unblocked

## References

- Plan: Phase 3 section
- Code anchors:
  - `src/plutus/db/models.py` — add MarketRegimeSnapshot
  - `src/plutus/data/ohlcv.py:205` — reused `fetch_ohlcv`
  - `src/plutus/agents/graph.py:162` — graph wiring
