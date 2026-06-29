# Phase Dashboard — Surfacing Pass

```yaml
phase_id: phase_dashboard
status: pending
depends_on: [phase_1, phase_3a, phase_4a, phase_7]
blocks: []
estimated_effort: 3 days
test_framework: streamlit.testing.v1.AppTest
```

## Goal

Surface every new metric produced by prior phases on the existing dashboard tabs. No new pages — extend `src/plutus/dashboard/*` in place.

## Acceptance criteria

- [ ] **Per-row in Signals tab**: composite score, sub-score breakdown (5 pillars), ATR-anchored stop/target, R:R, position size (shares + ₹ exposure + ₹ risk), distance from EMA20/EMA50, sector + sector RS rank, F&O ban flag, material event flag
- [ ] **Top-of-page badges** on Home tab: Nifty regime (BULL/BEAR/SIDEWAYS + EMA50 distance), top 3 sectors by RS, count of material events open, trailing-30d realized win rate
- [ ] **Score tooltip**: hovering a score shows "Bucket 70–80: 58% historical win rate (n=47)" — only when Phase 4c calibration data exists for that bucket
- [ ] **Watchlist auto-tag**: top 5 by composite score get a `[high-conviction]` tag
- [ ] No existing tab loses functionality

## Task list

### Parallel group D1 — Signals tab columns (TASK-D.1 through TASK-D.4)

### TASK-D.1 — Sub-score column

```yaml
parallelizable: yes
parallel_group: D1
estimated_effort: 2h
```

**Test first**:
```python
# tests/dashboard/test_signals_columns.py
def test_signals_dataframe_has_sub_scores(db_session):
    seed_recommendation(db_session, technical_score=80, smart_money_score=60,
                        sentiment_score=70, regime_score=75, rr_score=85)
    at = AppTest.from_file("src/plutus/dashboard/signals.py")
    at.run()
    df = at.dataframe[0].value
    for col in ["tech", "smart_money", "sentiment", "regime", "rr"]:
        assert col in df.columns
```

**Files to modify**: `src/plutus/dashboard/signals.py`.

---

### TASK-D.2 — ATR / R:R / position-size columns

```yaml
parallelizable: yes
parallel_group: D1
estimated_effort: 2h
```

**Test first**:
```python
def test_signals_have_position_sizing(db_session):
    seed_recommendation(db_session, entry_mid=1500, stop_loss=1470, target1=1560,
                        rr_ratio=2.0, ...)
    at = AppTest.from_file("src/plutus/dashboard/signals.py")
    at.run()
    df = at.dataframe[0].value
    assert "R:R" in df.columns
    assert "Shares" in df.columns
    assert "Exposure ₹" in df.columns
    assert "Risk ₹" in df.columns
```

---

### TASK-D.3 — EMA distance + sector + RS columns

```yaml
parallelizable: yes
parallel_group: D1
estimated_effort: 2h
```

**Test first**:
```python
def test_signals_have_ema_distance(db_session):
    seed_recommendation(db_session, ...)
    at = AppTest.from_file("src/plutus/dashboard/signals.py")
    at.run()
    df = at.dataframe[0].value
    assert "EMA20 dist %" in df.columns
    assert "EMA50 dist %" in df.columns
    assert "Sector" in df.columns
    assert "Sector RS" in df.columns
```

---

### TASK-D.4 — F&O ban / material event flag columns

```yaml
parallelizable: yes
parallel_group: D1
estimated_effort: 1h
```

**Test first**:
```python
def test_fno_ban_flag_renders(db_session, monkeypatch):
    monkeypatch.setattr("plutus.data.universe.fetch_fno_ban_list",
                        lambda: {"RELIANCE"})
    seed_recommendation(db_session, symbol="RELIANCE")
    at = AppTest.from_file("src/plutus/dashboard/signals.py")
    at.run()
    df = at.dataframe[0].value
    reliance = df[df["symbol"] == "RELIANCE"].iloc[0]
    assert reliance["F&O ban"] is True or reliance["F&O ban"] == "🚫"
```

---

### TASK-D.5 — Nifty regime badge (Home tab)

```yaml
parallelizable: yes
parallel_group: D2
estimated_effort: 2h
```

**Test first**:
```python
def test_regime_badge_bull(monkeypatch):
    monkeypatch.setattr("plutus.data.regime.get_nifty_regime",
                        lambda: {"trend": "BULL", "slope": 0.45, "distance_from_ema50_pct": 3.5})
    at = AppTest.from_file("src/plutus/dashboard/home.py")
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Nifty Regime"] == "BULL"
    assert "+3.5%" in metrics.get("Distance from EMA50", "")
```

**Files to modify**: `src/plutus/dashboard/home.py`.

---

### TASK-D.6 — Top 3 sectors badge

```yaml
parallelizable: yes
parallel_group: D2
estimated_effort: 1h
```

**Test first**:
```python
def test_top_3_sectors_render(monkeypatch):
    monkeypatch.setattr("plutus.data.regime.get_sector_strength",
                        lambda: {"IT": 1.20, "BANK": 1.15, "AUTO": 1.10, "FMCG": 1.05, "PHARMA": 0.95})
    at = AppTest.from_file("src/plutus/dashboard/home.py")
    at.run()
    # Top 3 displayed
    badges = [md.value for md in at.markdown if "Top sectors" in md.value]
    assert any("IT" in b and "BANK" in b and "AUTO" in b for b in badges)
```

---

### TASK-D.7 — Material events count + trailing-30d win rate

```yaml
parallelizable: yes
parallel_group: D2
estimated_effort: 2h
```

**Test first**:
```python
def test_material_events_count(db_session):
    seed_news_events(db_session, [
        {"is_material": True, "published_at": datetime.utcnow() - timedelta(hours=12)},
        {"is_material": True, "published_at": datetime.utcnow() - timedelta(hours=20)},
        {"is_material": False, ...},
    ])
    at = AppTest.from_file("src/plutus/dashboard/home.py")
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Material Events"] == "2"

def test_30d_win_rate(db_session):
    seed_closed_outcomes(db_session, [
        {"outcome": "HIT_T1", "outcome_date": date.today() - timedelta(days=5)},
        {"outcome": "STOPPED", "outcome_date": date.today() - timedelta(days=10)},
        {"outcome": "HIT_T2", "outcome_date": date.today() - timedelta(days=15)},
    ])
    at = AppTest.from_file("src/plutus/dashboard/home.py")
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["30d Win Rate"] == "66.7%"
```

---

### TASK-D.8 — Score tooltip with calibration data

```yaml
parallelizable: no
parallel_group: null
reason: Requires Phase 4c calibration data; sequential.
estimated_effort: 2h
```

**Test first**:
```python
def test_tooltip_shows_when_calibration_exists(db_session):
    seed_calibration(db_session, [{"bucket": "70-80", "n": 47, "win_rate": 0.58}])
    seed_recommendation(db_session, symbol="RELIANCE", confidence=75)
    at = AppTest.from_file("src/plutus/dashboard/signals.py")
    at.run()
    # Streamlit uses help= parameter on columns/metrics for tooltips
    df = at.dataframe[0].value
    # The tooltip text is captured by column config metadata
    # AppTest may not directly expose help; verify via the column config
    ...

def test_no_tooltip_when_no_calibration(db_session):
    seed_recommendation(db_session, symbol="RELIANCE", confidence=75)
    at = AppTest.from_file("src/plutus/dashboard/signals.py")
    at.run()
    # No calibration row exists; tooltip empty
    ...
```

**Files to modify**: `src/plutus/dashboard/signals.py` — use `st.column_config.Column(help=...)`.

---

### TASK-D.9 — Watchlist auto-tag top 5 high-conviction

```yaml
parallelizable: yes
parallel_group: D3
estimated_effort: 2h
```

**Test first**:
```python
def test_top_5_get_high_conviction_tag(db_session):
    seed_recommendations(db_session, [
        {"symbol": f"SYM{i}", "confidence": 100 - i} for i in range(10)
    ])
    at = AppTest.from_file("src/plutus/dashboard/watchlist.py")
    at.run()
    df = at.dataframe[0].value
    top_5 = df.nlargest(5, "confidence")["symbol"].tolist()
    tagged = df[df["high_conviction"] == True]["symbol"].tolist()
    assert set(top_5) == set(tagged)
```

**Files to modify**: `src/plutus/dashboard/watchlist.py`.

## Streamlit considerations

- **`st.column_config`** used for column-level tooltips and number formatting
- **`st.metric` deltas** support coloured up/down indicators for regime badges
- **Conditional rendering**: badges only show when data exists; tests must seed data first

## Verification

```bash
pytest tests/dashboard/ -v
# Manual: run weekly pipeline end-to-end, then walk every tab
```

## Done definition

- [ ] All 9 tasks complete; tests green
- [ ] No existing tab regressed
- [ ] Manual walkthrough of all 8 tabs documented in PR

## References

- Plan: Dashboard surfacing section
- Code anchors:
  - `src/dashboard.py:367–423` — Signals tab current
  - `src/plutus/dashboard/*` — extension points
