# Phase 4c — Score Bucket Calibration

```yaml
phase_id: phase_4c
status: pending
depends_on: [phase_4a]
blocks: [phase_4_5]
estimated_effort: 1 day
test_framework: pytest
```

## Goal

After ≥ 30 closed recommendations exist in the audit table, compute realized win rate per score bucket. Surface "Score 70–80 bucket: 58% win rate (n=47)" in the dashboard tooltip. This is the data side of self-finetuning (Phase 4.5 reads from the same table).

## Acceptance criteria

- [ ] `compute_bucket_calibration(min_n=30)` reads `trade_outcomes_audit`, writes `score_bucket_calibration` rows
- [ ] Buckets: `0-10, 10-20, ..., 90-100` (10-point bands)
- [ ] Each bucket row: `n`, `win_rate`, `avg_mfe_pct`, `avg_mae_pct`, `avg_hold_days_actual`, `last_updated`
- [ ] Weekly cron job appended to weekly_pipeline Sunday run
- [ ] Dashboard tooltip data available via `get_bucket_stats(bucket: str) -> dict | None`

## Task list

### TASK-4c.1 — Schema: `score_bucket_calibration`

```yaml
parallelizable: no
estimated_effort: 20min
```

**Test first**:
```python
def test_calibration_row(db_session):
    from plutus.db.models import ScoreBucketCalibration
    row = ScoreBucketCalibration(bucket="70-80", n=47, win_rate=0.58,
                                 avg_mfe_pct=4.2, avg_mae_pct=-1.8, avg_hold_days_actual=5.4,
                                 last_updated=datetime.utcnow())
    db_session.add(row); db_session.commit()
```

---

### TASK-4c.2 — Aggregation job

```yaml
parallelizable: no
estimated_effort: 2h
```

**Test first**:
```python
def test_aggregation_skips_low_n_buckets(db_session, monkeypatch):
    # Seed 25 outcomes in bucket 60-70 (below min_n=30) and 35 in 70-80
    seed_outcomes(db_session, [...])
    compute_bucket_calibration(min_n=30)
    assert db_session.query(ScoreBucketCalibration).filter_by(bucket="60-70").count() == 0
    assert db_session.query(ScoreBucketCalibration).filter_by(bucket="70-80").count() == 1

def test_win_rate_calculation():
    # 20 of 35 outcomes are HIT_T1 or HIT_T2 ⇒ win_rate=0.571
    ...
    compute_bucket_calibration(min_n=30)
    row = db_session.query(ScoreBucketCalibration).filter_by(bucket="70-80").one()
    assert row.win_rate == pytest.approx(0.571, abs=0.01)

def test_mfe_mae_averages():
    ...
```

**Files to create**:
- `src/plutus/weekly/calibration.py` — `compute_bucket_calibration(min_n=30)`.

---

### TASK-4c.3 — `get_bucket_stats(bucket)` helper

```yaml
parallelizable: yes
parallel_group: 4C_consumers
estimated_effort: 30min
```

**Test first**:
```python
def test_get_bucket_stats_returns_none_when_no_data(db_session):
    assert get_bucket_stats("90-100") is None

def test_get_bucket_stats_returns_dict_when_data(db_session):
    seed_calibration(db_session, [...])
    s = get_bucket_stats("70-80")
    assert s["n"] >= 30
    assert 0 <= s["win_rate"] <= 1
```

---

### TASK-4c.4 — Wire into weekly pipeline

```yaml
parallelizable: yes
parallel_group: 4C_consumers
estimated_effort: 30min
```

**Test first**:
```python
def test_weekly_pipeline_calls_calibration(db_session, monkeypatch):
    called = []
    monkeypatch.setattr("plutus.weekly.calibration.compute_bucket_calibration",
                        lambda **kw: called.append(kw))
    weekly_pipeline()
    assert len(called) == 1
```

**Files to modify**: `main.py` — add `compute_bucket_calibration()` to weekly pipeline.

## Streamlit considerations

The tooltip rendering lands in `phase_dashboard.md`. Test seam: `get_bucket_stats()` is the public read API.

## Verification

```bash
pytest tests/test_calibration/ -v
# After 30+ closed trades in audit:
python -c "from plutus.weekly.calibration import compute_bucket_calibration; compute_bucket_calibration()"
```

## Done definition

- [ ] All 4 tasks complete
- [ ] Tests green
- [ ] Phase 4.5 unblocked once ≥ 30 trades accumulated

## References

- Plan: Phase 4c section
- Code anchors:
  - `src/plutus/weekly/outcomes.py` — produces audit rows
