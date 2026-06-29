# Phase 4a — Outcome Tracker

```yaml
phase_id: phase_4a
status: pending
depends_on: [phase_0]
blocks: [phase_4b, phase_4c, phase_4_5, phase_7]
estimated_effort: 3 days
test_framework: pytest
```

## Goal

Today, outcome tracking is commented out at `main.py:37` (`# from plutus.weekly.outcomes import track_recommendation_outcomes`). With no ground truth, the score cannot be validated. This phase ships a daily Mon–Fri 16:30 IST job that walks forward through each open recommendation's daily OHLCV, classifies it as `HIT_T1` / `HIT_T2` / `STOPPED` / `EXPIRED` / `WRONG_DIRECTION`, captures MFE and MAE, and tags the row with the score bucket + bundle + regime at signal time. This is the foundation for Phase 4c (calibration) and Phase 4.5 (self-finetuning).

## Acceptance criteria

- [ ] `track_recommendation_outcomes()` callable from `main.py`; daily job wired
- [ ] Five outcome enum values: `HIT_T1`, `HIT_T2`, `STOPPED`, `EXPIRED`, `WRONG_DIRECTION`
- [ ] `WRONG_DIRECTION` defined as: BUY signal where price drops through SL within 3 trading days
- [ ] MFE/MAE captured per closed recommendation
- [ ] Outcome row tagged with score bucket (e.g., `"70-80"`), bundle name, regime at signal time
- [ ] Backfill capability: replay 30/60/90-day historical recommendations in one CLI run

## Prerequisites

- Phase 0 done — OHLCV is reliable

## Task list

### TASK-4a.1 — Schema: `trade_outcomes_audit` + outcome enum extension

```yaml
parallelizable: no
parallel_group: null
estimated_effort: 1h
```

**Test first**:
```python
def test_trade_outcomes_audit_row(db_session):
    from plutus.db.models import TradeOutcomesAudit
    row = TradeOutcomesAudit(
        recommendation_id=1, outcome="HIT_T1", outcome_date=date.today(),
        mfe_pct=4.5, mae_pct=-1.2,
        score_bucket="70-80", bundle="trend", regime_at_signal="BULL",
        hold_days_actual=4,
    )
    db_session.add(row); db_session.commit()

def test_outcome_enum_includes_wrong_direction():
    from plutus.db.models import OutcomeEnum
    assert "WRONG_DIRECTION" in {e.value for e in OutcomeEnum}
```

**Files to modify**:
- `src/plutus/db/models.py:70–106` — extend `outcome` enum; add `TradeOutcomesAudit` model.
- `src/plutus/db/schema.sql`.
- `migrations/00X_phase4a_outcomes.sql`.

**Acceptance**: migration runs; tests green.

---

### TASK-4a.2 — `classify_outcome()` pure function

```yaml
parallelizable: no
parallel_group: null
reason: TASK-4a.3 depends on this.
estimated_effort: 3h
```

**Test first**:
```python
# tests/test_outcomes/test_classify.py
from plutus.weekly.outcomes import classify_outcome

def test_hit_t1_first():
    """Price hits T1 on day 2; that's the outcome (not T2 later)."""
    rec = Rec(entry=100, sl=98, t1=104, t2=106, signal_date=date(2026, 6, 1), hold_days_max=10, side="long")
    bars = make_bars([
        (date(2026, 6, 1), 100, 101, 99, 100.5),
        (date(2026, 6, 2), 100.5, 104.5, 100, 104.2),   # T1 hit intraday
        (date(2026, 6, 3), 104, 107, 103, 106.5),       # T2 also hit later, but we score T1 first
    ])
    out = classify_outcome(rec, bars)
    assert out["outcome"] == "HIT_T1"
    assert out["outcome_date"] == date(2026, 6, 2)

def test_stopped_before_t1():
    rec = Rec(entry=100, sl=98, t1=104, t2=106, ..., side="long")
    bars = make_bars([(date(2026, 6, 1), 100, 100.5, 97, 97.5)])
    out = classify_outcome(rec, bars)
    assert out["outcome"] == "STOPPED"

def test_wrong_direction_3_day_window():
    """BUY signal, price drops through SL within 3 trading days = WRONG_DIRECTION (subset of STOPPED)."""
    rec = Rec(entry=100, sl=98, t1=104, t2=106, signal_date=date(2026, 6, 1), side="long")
    bars = make_bars([
        (date(2026, 6, 1), 100, 100.5, 97.5, 98),       # touches SL day 1
    ])
    out = classify_outcome(rec, bars)
    assert out["outcome"] == "WRONG_DIRECTION"

def test_expired_at_hold_days_max():
    """Hold days reached without hitting any level."""
    rec = Rec(entry=100, sl=98, t1=104, t2=106, signal_date=date(2026, 6, 1),
              hold_days_max=5, side="long")
    bars = make_bars([(date(2026, 6, i), 100, 101, 99, 100.5) for i in range(1, 7)])
    out = classify_outcome(rec, bars)
    assert out["outcome"] == "EXPIRED"
    assert out["hold_days_actual"] == 5

def test_mfe_mae_computed():
    rec = Rec(entry=100, sl=98, t1=104, t2=106, side="long")
    bars = make_bars([
        (date(2026, 6, 1), 100, 103, 99, 102.5),   # MFE=3 so far, MAE=-1
        (date(2026, 6, 2), 102, 105, 102, 104.2),  # T1 hit; MFE=5 at peak
    ])
    out = classify_outcome(rec, bars)
    assert out["mfe_pct"] == pytest.approx(5.0, abs=0.1)
    assert out["mae_pct"] == pytest.approx(-1.0, abs=0.1)
```

**Files to create**:
- `src/plutus/weekly/outcomes.py` — `classify_outcome(rec, bars) -> dict`.

**Algorithm**:
1. For each bar from `signal_date` to `signal_date + hold_days_max`:
   - If `high >= t1` (long): mark T1 hit. If `high >= t2`, prefer T2 if same bar. Else T1.
   - If `low <= sl` (long): mark stopped. If within 3 trading days ⇒ `WRONG_DIRECTION`; else `STOPPED`.
   - Update MFE/MAE.
2. If reach `hold_days_max` without exit: `EXPIRED`.
3. Trading day arithmetic via `trading_calendar.py`.

**Acceptance**: all 5 tests green.

---

### TASK-4a.3 — `track_recommendation_outcomes()` job

```yaml
parallelizable: no
parallel_group: null
estimated_effort: 2h
```

**Test first**:
```python
def test_job_marks_open_recs_only(db_session, monkeypatch):
    # seed 3 OPEN recs and 2 CLOSED recs
    seed_recommendations(db_session, [...])
    monkeypatch.setattr("plutus.weekly.outcomes.fetch_ohlcv", lambda *a, **kw: bars_with_t1_hit)
    track_recommendation_outcomes()
    closed_after = db_session.query(Recommendation).filter_by(outcome="HIT_T1").count()
    assert closed_after == 3   # only the 3 open ones got updated

def test_job_writes_audit_row(db_session, monkeypatch):
    seed_recommendations(db_session, [...])
    track_recommendation_outcomes()
    audit_rows = db_session.query(TradeOutcomesAudit).all()
    assert len(audit_rows) >= 1
    assert audit_rows[0].score_bucket is not None
```

**Files to modify**:
- `src/plutus/weekly/outcomes.py` — add `track_recommendation_outcomes()` that:
  1. Queries `Recommendation` where `outcome IS NULL`.
  2. For each: fetches OHLCV from signal_date forward, calls `classify_outcome`, writes outcome + audit row.
- `main.py:37` — uncomment the import; add the daily 16:30 IST job to the scheduler.

**Acceptance**: both tests green.

---

### TASK-4a.4 — Backfill CLI

```yaml
parallelizable: yes
parallel_group: 4A_post
estimated_effort: 1h
```

**Test first**:
```python
def test_backfill_30_days(db_session, monkeypatch):
    # seed historical recs older than 30 days
    ...
    from plutus.scripts.backfill_outcomes import main as backfill
    backfill(days=30)
    assert db_session.query(TradeOutcomesAudit).count() >= 1
```

**Files to create**:
- `src/plutus/scripts/backfill_outcomes.py` — `python -m plutus.scripts.backfill_outcomes --days 90`.

**Acceptance**: replay completes; audit rows match hand-checked spreadsheet for 10 sample recommendations.

---

### TASK-4a.5 — Score bucket tagging helper

```yaml
parallelizable: yes
parallel_group: 4A_post
estimated_effort: 30min
```

**Test first**:
```python
def test_bucket_assignment():
    from plutus.weekly.outcomes import score_to_bucket
    assert score_to_bucket(75) == "70-80"
    assert score_to_bucket(69.99) == "60-70"
    assert score_to_bucket(0) == "0-10"
    assert score_to_bucket(100) == "90-100"
```

**Files to modify**: `src/plutus/weekly/outcomes.py` — add `score_to_bucket(score: float) -> str`.

**Acceptance**: edge cases green.

## Streamlit considerations

The Portfolio tab consumes this data (Phase 7). Trade history table shows MFE/MAE per closed trade. No direct Streamlit work in this phase.

## Verification

```bash
pytest tests/test_outcomes/ -v
python -m plutus.scripts.backfill_outcomes --days 60
# Inspect: db_session.query(TradeOutcomesAudit).all()
```

## Done definition

- [ ] All 5 tasks complete
- [ ] Daily job runs successfully for 1 week without errors
- [ ] Backfill produces audit rows for at least 10 historical recommendations

## References

- Plan: Phase 4a section
- Code anchors:
  - `main.py:37` — commented import to enable
  - `src/plutus/db/models.py:70–106` — Recommendation model has outcome fields already
  - `src/plutus/data/ohlcv.py:205` — used to walk forward
  - `src/plutus/utils/trading_calendar.py` — NSE day arithmetic
