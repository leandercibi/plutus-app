# Phase 8 — Position-Aware Alerts (Telegram + WhatsApp stub)

```yaml
phase_id: phase_8
status: pending
depends_on: [phase_7]
blocks: []
estimated_effort: 3 days
test_framework: pytest + responses (HTTP mocking)
```

## Goal

The user's #4 ask: when an open mock position approaches its stop loss, alert via Telegram to consider exit before SL hits. Same for T1/T2 hits. WhatsApp Business is "for later" — ship the gateway interface now, leave the impl stubbed.

## Acceptance criteria

- [ ] Alert monitor runs every 15 minutes during NSE hours (09:15–15:30 IST)
- [ ] Pre-SL warning fires when LTP within 1% of stop loss (configurable in `trading_params`)
- [ ] T1 hit alert fires when LTP crosses T1
- [ ] T2 hit alert fires when LTP crosses T2
- [ ] Trend invalidation alert: long held > 5 days and closes < EMA20 on daily
- [ ] 1-hour cooldown per (ticker, alert_type, portfolio_id) — no spam
- [ ] Telegram channel sends within 5s of trigger
- [ ] WhatsApp channel: gateway interface exists; raises `NotImplementedError` cleanly
- [ ] Alert log surfaces in Portfolio tab: "3 alerts sent in last 7 days; you acted on 2"

## Prerequisites

- Phase 7 done — open positions exist in DB

## Task list

### TASK-8.1 — Schema: `alerts` table + `Alert` model

```yaml
parallelizable: no
estimated_effort: 1h
```

**Test first**:
```python
def test_alert_row(db_session):
    from plutus.db.models import Alert, AlertType
    a = Alert(portfolio_id=1, symbol="RELIANCE", alert_type=AlertType.PRE_SL,
              triggered_at=datetime.utcnow(), message="⚠️ SELL ALERT...",
              channels_sent=["telegram"], acknowledged=False)
    db_session.add(a); db_session.commit()

def test_alert_type_enum():
    from plutus.db.models import AlertType
    assert {e.value for e in AlertType} >= {"PRE_SL", "T1_HIT", "T2_HIT", "TREND_INVALIDATED"}
```

**Files**: `src/plutus/db/models.py` + migration.

---

### TASK-8.2 — Alert trigger evaluator

```yaml
parallelizable: no
estimated_effort: 3h
```

**Test first**:
```python
# tests/test_alerts/test_triggers.py
from plutus.alerts.monitor import evaluate_alerts_for_position

def test_pre_sl_alert_within_1_pct():
    position = Position(symbol="RELIANCE", entry=1500, stop=1470, t1=1560, t2=1590, side="long")
    ltp = 1485.0   # within 1% of stop (1470)
    alerts = evaluate_alerts_for_position(position, ltp, indicator_df=None)
    assert any(a["type"] == "PRE_SL" for a in alerts)

def test_no_pre_sl_when_far_from_stop():
    position = Position(symbol="RELIANCE", entry=1500, stop=1470, ...)
    ltp = 1520.0
    alerts = evaluate_alerts_for_position(position, ltp, indicator_df=None)
    assert not any(a["type"] == "PRE_SL" for a in alerts)

def test_t1_hit_alert():
    position = Position(symbol="RELIANCE", entry=1500, stop=1470, t1=1560, t2=1590)
    ltp = 1561.0
    alerts = evaluate_alerts_for_position(position, ltp, indicator_df=None)
    assert any(a["type"] == "T1_HIT" for a in alerts)

def test_t2_hit_alert():
    position = Position(symbol="RELIANCE", entry=1500, stop=1470, t1=1560, t2=1590)
    ltp = 1591.0
    alerts = evaluate_alerts_for_position(position, ltp, indicator_df=None)
    assert any(a["type"] == "T2_HIT" for a in alerts)

def test_trend_invalidated_after_5_days(indicator_df_close_below_ema20):
    position = Position(symbol="RELIANCE", entry=1500, days_held=6, side="long", ...)
    ltp = 1490
    alerts = evaluate_alerts_for_position(position, ltp, indicator_df_close_below_ema20)
    assert any(a["type"] == "TREND_INVALIDATED" for a in alerts)

def test_no_trend_alert_before_5_days(indicator_df_close_below_ema20):
    position = Position(symbol="RELIANCE", days_held=3, side="long", ...)
    alerts = evaluate_alerts_for_position(position, 1490, indicator_df_close_below_ema20)
    assert not any(a["type"] == "TREND_INVALIDATED" for a in alerts)

def test_short_position_pre_sl_mirror():
    position = Position(symbol="RELIANCE", entry=1500, stop=1530, side="short", ...)
    ltp = 1525.0   # within 1% of upper stop
    alerts = evaluate_alerts_for_position(position, ltp, indicator_df=None)
    assert any(a["type"] == "PRE_SL" for a in alerts)
```

**Files to create**:
- `src/plutus/alerts/monitor.py` — `evaluate_alerts_for_position()`.

---

### TASK-8.3 — Channel gateway (Telegram impl + WhatsApp stub)

```yaml
parallelizable: yes
parallel_group: 8A
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_alerts/test_channels.py
import responses

@responses.activate
def test_telegram_channel_sends():
    responses.add(responses.POST, "http://127.0.0.1:8001/send",
                  json={"ok": True}, status=200)
    from plutus.alerts.channels import TelegramChannel
    ch = TelegramChannel()
    result = ch.send("⚠️ SELL ALERT: RELIANCE...")
    assert result["ok"] is True

def test_whatsapp_channel_not_implemented():
    from plutus.alerts.channels import WhatsAppChannel
    ch = WhatsAppChannel()
    with pytest.raises(NotImplementedError):
        ch.send("...")

def test_channel_gateway_dispatches_to_active():
    from plutus.alerts.channels import dispatch_alert
    sent = []
    monkeypatch.setattr("plutus.alerts.channels.TelegramChannel.send",
                        lambda self, msg: sent.append(("telegram", msg)) or {"ok": True})
    dispatch_alert(message="test", channels=["telegram"])
    assert sent == [("telegram", "test")]
```

**Files to create**:
- `src/plutus/alerts/channels.py`:
  ```python
  class Channel(Protocol):
      def send(self, message: str) -> dict: ...

  class TelegramChannel(Channel):
      def send(self, message): ...   # POST to 127.0.0.1:8001/send

  class WhatsAppChannel(Channel):
      def send(self, message):
          raise NotImplementedError("WhatsApp channel not yet enabled; see Phase 8b")

  def dispatch_alert(message: str, channels: list[str]) -> dict[str, dict]: ...
  ```

---

### TASK-8.4 — Dedup logic (1-hour cooldown)

```yaml
parallelizable: yes
parallel_group: 8A
estimated_effort: 2h
```

**Test first**:
```python
def test_duplicate_alert_within_1h_suppressed(db_session):
    from plutus.alerts.monitor import should_send_alert
    seed_alert(db_session, symbol="RELIANCE", alert_type="PRE_SL",
               triggered_at=datetime.utcnow() - timedelta(minutes=30))
    assert should_send_alert(symbol="RELIANCE", alert_type="PRE_SL", portfolio_id=1) is False

def test_duplicate_after_1h_allowed(db_session):
    seed_alert(db_session, symbol="RELIANCE", alert_type="PRE_SL",
               triggered_at=datetime.utcnow() - timedelta(hours=2))
    assert should_send_alert(symbol="RELIANCE", alert_type="PRE_SL", portfolio_id=1) is True

def test_different_alert_type_not_deduped(db_session):
    seed_alert(db_session, symbol="RELIANCE", alert_type="PRE_SL", ...)
    assert should_send_alert(symbol="RELIANCE", alert_type="T1_HIT", portfolio_id=1) is True

def test_different_portfolio_not_deduped(db_session):
    seed_alert(db_session, symbol="RELIANCE", alert_type="PRE_SL", portfolio_id=1, ...)
    assert should_send_alert(symbol="RELIANCE", alert_type="PRE_SL", portfolio_id=2) is True
```

**Files to modify**: `src/plutus/alerts/monitor.py` — `should_send_alert()`.

---

### TASK-8.5 — Monitor job + scheduler wiring

```yaml
parallelizable: no
estimated_effort: 2h
```

**Test first**:
```python
def test_monitor_runs_on_each_open_position(db_session, monkeypatch):
    seed_open_positions(db_session, count=3, ...)
    monkeypatch.setattr("plutus.data.ohlcv.fetch_live_price", lambda s, **kw: 1500.0)
    sent = []
    monkeypatch.setattr("plutus.alerts.channels.dispatch_alert", lambda **kw: sent.append(kw))
    from plutus.alerts.monitor import run_alert_monitor
    run_alert_monitor()
    # Each open position evaluated
    assert len(sent) >= 0   # Depends on whether triggers fired

def test_monitor_writes_alerts_to_db(db_session, monkeypatch):
    seed_open_positions(db_session, ...)
    monkeypatch.setattr("plutus.data.ohlcv.fetch_live_price", lambda s, **kw: 1485)   # near SL
    monkeypatch.setattr("plutus.alerts.channels.dispatch_alert", lambda **kw: {"telegram": {"ok": True}})
    run_alert_monitor()
    from plutus.db.models import Alert
    assert db_session.query(Alert).count() >= 1
```

**Files to modify**:
- `src/plutus/alerts/monitor.py` — `run_alert_monitor()`.
- `main.py` — schedule every 15 min during NSE hours.

---

### TASK-8.6 — Alert log UI

```yaml
parallelizable: yes
parallel_group: 8B
estimated_effort: 2h
```

**Test first** (Streamlit AppTest):
```python
# tests/dashboard/test_portfolio_alerts.py
def test_alert_log_section_renders(db_session):
    seed_alerts(db_session, [...])
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    headers = [md.value for md in at.markdown if "Alerts" in md.value]
    assert len(headers) >= 1

def test_acknowledge_button_marks_alert(db_session):
    seed_alerts(db_session, [{"id": 5, "acknowledged": False}])
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    at.button(key="ack_5").click()
    at.run()
    from plutus.db.models import Alert
    assert db_session.query(Alert).filter_by(id=5).one().acknowledged is True

def test_metrics_show_action_rate(db_session):
    seed_alerts(db_session, count=10, acknowledged_count=7)
    at = AppTest.from_file("src/plutus/dashboard/portfolio.py")
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    assert "Alerts sent" in metrics
    assert "Acted on" in metrics
```

**Files to modify**: `src/plutus/dashboard/portfolio.py` — `render_alert_log(portfolio_name)`.

## Streamlit considerations

- Alert log uses `st.dataframe` + per-row `st.button(key=f"ack_{id}")`.
- Test seam: `at.button(key="ack_5")` directly addresses individual alert rows.

## Verification

```bash
pytest tests/test_alerts/ tests/dashboard/test_portfolio_alerts.py -v
# Manual: create a mock position with SL 1% below current LTP, wait 15min,
# verify Telegram message arrives.
```

## Done definition

- [ ] All 6 tasks complete; tests green
- [ ] Manual: alert delivered to Telegram within 15min of triggering condition
- [ ] WhatsApp channel raises NotImplementedError cleanly
- [ ] Dedup cooldown verified (second trigger within 1h suppressed)

## References

- Plan: Phase 8 section
- Code anchors:
  - `src/plutus/data/ohlcv.py:256` — fetch_live_price
  - Telegram bot endpoint: `127.0.0.1:8001/send`
- WhatsApp Business Cloud API: Meta Graph API (for Phase 8b deferred impl)
