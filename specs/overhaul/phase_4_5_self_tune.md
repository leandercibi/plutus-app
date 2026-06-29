# Phase 4.5 — Self-Finetuning Loop

```yaml
phase_id: phase_4_5
status: pending
depends_on: [phase_1, phase_4a, phase_4c]
blocks: []
estimated_effort: 4 days
test_framework: pytest + streamlit.testing.v1.AppTest
```

## Goal

The user's killer ask: "go back 30/60/90 days, check whether recommendations hit target / SL / were wrong, and have the system fine-tune itself."

Three concentric loops:
1. **Reporting** (always on) — replays closed trades, writes calibration report appended to weekly_runs.md.
2. **Suggestion** (gated, manual approval) — when divergence > 15pp persists 2 weeks, writes a tuning suggestion to `tuning_suggestions` table; user accepts/rejects via Settings UI.
3. **Auto-tuning** (opt-in flag, off by default) — narrow knobs only (Composite weights, bucket thresholds); compares 12-week trailing win rate before/after; rolls back on regression.

Borrowed pattern from tradermonty's `signal-postmortem` + `trader-memory-core` skills.

## Acceptance criteria

- [ ] Reporting loop runs Sunday before weekly pipeline, appends to `weekly_runs.md`
- [ ] Report includes: per-bucket win rate, per-bundle win rate, per-regime win rate, MFE/MAE per bucket, top 5 best / worst calls, WRONG_DIRECTION count
- [ ] Suggestion loop writes rows when divergence > 15pp for ≥ 2 consecutive weekly reports AND `n ≥ 30`
- [ ] Settings UI displays suggestion queue with `[Apply] [Reject] [Defer]` actions
- [ ] Applying a suggestion logs to `tuning_history` and the next weekly pipeline uses new weights
- [ ] Auto-tuning loop is opt-in via `trading_params.auto_tune_enabled` (default false)
- [ ] Auto-tuning rolls back if win rate drops > 5pp over 4 weeks

## Prerequisites

- Phase 4a producing audit rows
- Phase 4c producing calibration rows
- Phase 1 sub-scores in `Recommendation` table

## Task list

### TASK-4.5.1 — Schema: `tuning_suggestions` + `tuning_history`

```yaml
parallelizable: no
estimated_effort: 30min
```

**Test first**:
```python
def test_tuning_suggestion_row(db_session):
    from plutus.db.models import TuningSuggestion
    s = TuningSuggestion(
        created_date=date.today(), suggestion_type="bucket_weight_change",
        target="bucket_70_80", current_value=0.40, suggested_value=0.35,
        rationale="Realized win rate 38% vs target 60% over n=47",
        status="pending"   # pending | applied | rejected | deferred
    )
    db_session.add(s); db_session.commit()

def test_tuning_history_row(db_session):
    from plutus.db.models import TuningHistory
    h = TuningHistory(
        applied_date=date.today(), suggestion_id=1,
        param_changed="pillar_weight_technical", old_value=0.40, new_value=0.35,
        applied_by="leander", note="...",
    )
    db_session.add(h); db_session.commit()
```

**Files**: `src/plutus/db/models.py` + migration.

---

### TASK-4.5.2 — Reporting loop

```yaml
parallelizable: no
estimated_effort: 4h
```

**Test first**:
```python
# tests/test_self_tune/test_reporting.py
from plutus.weekly.postmortem import generate_calibration_report

def test_report_includes_bucket_section(db_session):
    seed_outcomes(db_session, BUCKET_SCENARIOS)
    report = generate_calibration_report(lookback_days=90)
    assert "Per-bucket performance" in report
    assert "70-80" in report

def test_report_includes_regime_section():
    report = generate_calibration_report(lookback_days=90)
    assert "Per-regime performance" in report
    assert "BULL" in report

def test_report_top_5_best_worst():
    report = generate_calibration_report(lookback_days=90)
    assert "Top 5 best calls" in report
    assert "Top 5 worst calls" in report

def test_report_wrong_direction_count():
    report = generate_calibration_report(lookback_days=90)
    assert "WRONG_DIRECTION:" in report

def test_report_appended_to_weekly_runs_md(tmp_path, monkeypatch):
    monkeypatch.setattr("plutus.weekly.postmortem.WEEKLY_RUNS_MD", tmp_path / "weekly_runs.md")
    generate_calibration_report(lookback_days=90, append=True)
    content = (tmp_path / "weekly_runs.md").read_text()
    assert "## Calibration Report" in content
```

**Files to create**:
- `src/plutus/weekly/postmortem.py` — `generate_calibration_report(lookback_days, append=True)`.

**Acceptance**: all 5 tests green.

---

### TASK-4.5.3 — Suggestion loop

```yaml
parallelizable: no
estimated_effort: 4h
```

**Test first**:
```python
def test_no_suggestion_when_divergence_below_threshold(db_session):
    # bucket 70-80: target 60%, actual 56% (4pp divergence; under 15pp)
    seed_outcomes_with_win_rate(db_session, bucket="70-80", win_rate=0.56, n=50)
    detect_tuning_opportunities()
    assert db_session.query(TuningSuggestion).count() == 0

def test_no_suggestion_when_n_below_30(db_session):
    seed_outcomes_with_win_rate(db_session, bucket="70-80", win_rate=0.30, n=25)
    detect_tuning_opportunities()
    assert db_session.query(TuningSuggestion).count() == 0

def test_suggestion_when_divergence_persists_2_weeks(db_session):
    # Week 1: bucket 70-80 win rate 38%; Week 2: still 35% (both > 15pp below target 60%)
    seed_outcomes_with_history(db_session, ...)
    detect_tuning_opportunities()
    detect_tuning_opportunities()   # second weekly run
    assert db_session.query(TuningSuggestion).filter_by(status="pending").count() == 1

def test_suggestion_text_includes_actual_numbers():
    seed_outcomes_with_win_rate(db_session, bucket="70-80", win_rate=0.38, n=47)
    detect_tuning_opportunities()
    s = db_session.query(TuningSuggestion).first()
    assert "38" in s.rationale
    assert "47" in s.rationale
```

**Files to create**:
- `src/plutus/weekly/tuner.py` — `detect_tuning_opportunities()`.

---

### TASK-4.5.4 — Settings UI: suggestion queue

```yaml
parallelizable: yes
parallel_group: 4_5_UI
estimated_effort: 4h
```

**Test first** (Streamlit AppTest):
```python
# tests/dashboard/test_settings_tuning.py
from streamlit.testing.v1 import AppTest

def test_tuning_tab_renders_empty_state(db_session):
    at = AppTest.from_file("src/plutus/dashboard/settings_tuning.py")
    at.run()
    assert any("No suggestions" in md.value for md in at.markdown)

def test_tuning_tab_shows_pending_suggestions(db_session, monkeypatch):
    seed_tuning_suggestions(db_session, [
        {"id": 1, "rationale": "Bucket 70-80...", "status": "pending"},
    ])
    at = AppTest.from_file("src/plutus/dashboard/settings_tuning.py")
    at.run()
    assert any("Bucket 70-80" in md.value for md in at.markdown)
    # Apply / Reject / Defer buttons exist
    btn_labels = {b.label for b in at.button}
    assert "Apply" in btn_labels
    assert "Reject" in btn_labels
    assert "Defer" in btn_labels

def test_apply_button_logs_to_history(db_session, monkeypatch):
    seed_tuning_suggestions(db_session, [{"id": 1, ...}])
    at = AppTest.from_file("src/plutus/dashboard/settings_tuning.py")
    at.run()
    at.button(key="apply_1").click()
    at.run()
    assert db_session.query(TuningHistory).count() == 1
    assert db_session.query(TuningSuggestion).filter_by(id=1).one().status == "applied"
```

**Files to create**:
- `src/plutus/dashboard/settings_tuning.py` — Streamlit page (a tab under Settings).

---

### TASK-4.5.5 — Auto-tuning loop (opt-in, off by default)

```yaml
parallelizable: yes
parallel_group: 4_5_UI
estimated_effort: 4h
```

**Test first**:
```python
def test_auto_tune_disabled_by_default(db_session):
    auto_tune_loop()   # should be a no-op
    assert db_session.query(TuningHistory).count() == 0

def test_auto_tune_only_adjusts_one_knob_per_week(db_session, monkeypatch):
    enable_auto_tune(db_session)
    seed_multiple_divergences(db_session, count=5)
    auto_tune_loop()
    assert db_session.query(TuningHistory).filter_by(applied_date=date.today()).count() == 1

def test_auto_tune_rolls_back_on_regression(db_session, monkeypatch):
    enable_auto_tune(db_session)
    apply_a_tune(db_session)
    # Simulate 4 weeks of regression
    seed_post_tune_regression(db_session, weeks=4, win_rate_drop_pp=6)
    auto_tune_check_rollback()
    h = db_session.query(TuningHistory).order_by(TuningHistory.applied_date.desc()).first()
    assert "rolled back" in h.note.lower()
```

**Files to modify**:
- `src/plutus/weekly/tuner.py` — `auto_tune_loop()`, `auto_tune_check_rollback()`.

## Streamlit considerations

Settings UI uses `st.tabs(["General", "Risk", "Tuning"])`. Test seam: `at.session_state["last_calibration_run"]`.

## Verification

```bash
pytest tests/test_self_tune/ tests/dashboard/test_settings_tuning.py -v
python -c "from plutus.weekly.postmortem import generate_calibration_report; print(generate_calibration_report(lookback_days=90))"
```

## Done definition

- [ ] All 5 tasks complete
- [ ] Reporting loop integrated into weekly pipeline
- [ ] Settings UI tab visible and functional
- [ ] Auto-tune disabled by default; opt-in works

## References

- Plan: Phase 4.5 section
- Code anchors:
  - `src/plutus/weekly/outcomes.py` — audit table source
  - `src/plutus/weekly/calibration.py` — bucket aggregates
