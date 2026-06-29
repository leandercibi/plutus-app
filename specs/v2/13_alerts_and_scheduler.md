# 13 — Alerts & Scheduler

> Telegram primary. WhatsApp optional. Decoupled cooldowns (A16). Scheduler runs Sunday full, Monday 09:10 re-validation (A15), daily exit monitor; midweek mini-screen (B18) gated by config.

---

## 1. Module layout

```
src/plutus/alerts/
├── __init__.py
├── channels.py            # AlertChannel protocol
├── telegram.py            # primary
├── whatsapp.py            # optional
├── formatter.py           # message templates
└── monitor.py             # ties exit_manager outputs to channels

src/plutus/scheduler/
├── __init__.py
├── jobs.py                # job functions
├── triggers.py            # APScheduler triggers
├── runner.py              # cli + service entry
└── run_log.py             # persistence of run history
```

---

## 2. `AlertChannel` protocol

```python
class AlertChannel(Protocol):
    name: str

    def send(self, message: AlertMessage) -> AlertResult: ...
```

```python
@dataclass(frozen=True)
class AlertMessage:
    kind: Literal["SL_BREACH", "SL_WARNING", "T1_HIT", "NO_PROGRESS", "ENTRY", "REGIME_FLIP", "THESIS_INVALIDATION", "MONDAY_REVALIDATION"]
    symbol: str | None
    title: str
    body_md: str
    severity: Literal["INFO", "WARNING", "URGENT"]
    deduplication_key: str   # for channel-side dedup
```

---

## 3. Telegram (`telegram.py`)

```python
class TelegramChannel:
    def __init__(self, token: SecretStr, chat_id: str): ...

    def send(self, message: AlertMessage) -> AlertResult:
        """
        POST to Telegram Bot API with Markdown V2 formatting.
        Retries x3 with exponential backoff on 5xx; never retries on 4xx.
        Returns AlertResult(success, telegram_message_id, error).
        """
```

Bot token and chat ID from settings. Single chat — operator's own.

---

## 4. WhatsApp (`whatsapp.py`)

Optional. Same `AlertChannel` interface. Disabled unless `settings.whatsapp_api_key` is set.

---

## 5. Formatter

```python
class AlertFormatter:
    def format_entry(self, signal: SwingSignal) -> AlertMessage: ...
    def format_sl_breach(self, trade: SwingTrade, fill: Fill) -> AlertMessage: ...
    def format_sl_warning(self, trade: SwingTrade, price: Decimal) -> AlertMessage: ...
    def format_t1_hit(self, trade: SwingTrade) -> AlertMessage: ...
    def format_no_progress(self, trade: SwingTrade) -> AlertMessage: ...
    def format_regime_flip(self, prior: RegimeVerdict, current: RegimeVerdict) -> AlertMessage: ...
    def format_thesis_invalidation(self, position: AccumulationPosition, reasons: list[str]) -> AlertMessage: ...
    def format_monday_revalidation(self, kept: list[SwingSignal], killed: list[tuple[SwingSignal, str]]) -> AlertMessage: ...
```

Each format method returns a fully populated `AlertMessage` with the right deduplication key (e.g., `f"{symbol}:{kind}:{date}"`).

---

## 6. Monitor (`monitor.py`)

```python
class AlertMonitor:
    def __init__(self, channels: list[AlertChannel], cooldown: CooldownPolicy, formatter: AlertFormatter): ...

    def emit(self, message: AlertMessage, session: Session) -> list[AlertResult]:
        """
        1. Check CooldownPolicy.can_fire(kind, symbol).
        2. If allowed: send to all channels, record AlertCooldown.last_fired_at.
        3. If not: log INFO and skip.
        SL_BREACH ALWAYS fires (A16 binding rule in CooldownPolicy).
        """
```

---

## 7. Scheduler jobs (`jobs.py`)

| Job | Trigger | Action |
|---|---|---|
| `sunday_full_run` | Cron Sun 19:00 IST | Build universe snapshot, fetch all data, run swing+accumulation pipelines, generate signals, write postmortem, send Telegram digest. |
| `monday_revalidation` | Cron Mon 09:10 IST | For each Sunday signal: re-run `swing/entries/monday_revalidation.py`; emit kept/killed alert (A15). |
| `daily_exit_monitor` | Cron Mon–Fri at 09:30, 10:15, 11:00, 13:30, 15:00 IST | Run `swing/exits/exit_manager.tick()` on all open trades; emit alerts. |
| `daily_freshness_check` | Cron Mon–Fri 09:05 IST | `assert_freshness`; on failure, abort that day's runs and alert URGENT. |
| `weekly_postmortem_publish` | Cron Sun 21:00 IST | Build the markdown postmortem, persist DB row, send Telegram link. |
| `midweek_mini_screen` | Cron Wed 19:00 IST | Gated by `settings.midweek_mini_screen_enabled` (B18). Runs Breakout + PEAD only. |

All times IST; APScheduler with `timezone="Asia/Kolkata"`.

---

## 8. Run log (`run_log.py`)

```python
class RunLog:
    def start(self, job_name: str) -> str:  # returns run_id
    def end(self, run_id: str, status: Literal["OK", "FAILED", "ABORTED"], details: dict) -> None
    def history(self, job_name: str, limit: int = 20) -> list[RunLogRow]
```

Surfaced on the dashboard "User flow" window.

---

## 9. Tests

| Test file | Cases |
|---|---|
| `tests/alerts/test_telegram_channel.py` | Successful POST → result.success. 500 retries 3x. 401 fails fast. |
| `tests/alerts/test_whatsapp_disabled_when_no_key.py` | No key → channel not constructed. |
| `tests/alerts/test_formatter_entry.py` | All fields present in markdown body; symbol bolded; dedup key correct. |
| `tests/alerts/test_formatter_regime_flip.py` | Includes prior + current label. |
| `tests/alerts/test_monitor_cooldown_respected.py` | Two fires within cooldown → only first sent. |
| `tests/alerts/test_monitor_sl_breach_always_fires.py` | (A16 hallmark) SL_WARNING just fired → SL_BREACH still fires immediately. |
| `tests/alerts/test_monitor_dedup_across_channels.py` | Two channels: both get same message; cooldown counts once. |
| `tests/scheduler/test_jobs_sunday_full.py` | End-to-end with fixtures: produces signals + postmortem; sends digest. |
| `tests/scheduler/test_jobs_monday_revalidation.py` | (A15 hallmark) Weekend gap fixture: signal killed, alert sent listing reason. |
| `tests/scheduler/test_jobs_daily_exit_monitor.py` | Fixture trade with SL touched today → SL_BREACH emitted at the next exit-monitor tick. |
| `tests/scheduler/test_jobs_freshness_aborts.py` | (B11 hallmark) Stale candle → run aborted, URGENT alert. |
| `tests/scheduler/test_jobs_midweek_gated_off.py` | settings.midweek_mini_screen_enabled=False → job is a no-op. |
| `tests/scheduler/test_run_log.py` | start → end pair persisted; history returns most recent. |
| `tests/scheduler/test_timezone_ist.py` | APScheduler triggers configured with `Asia/Kolkata`. |

---

## Acceptance criteria

- [ ] A16 hallmark green (SL_BREACH not suppressed).
- [ ] A15 hallmark green (Monday re-validation re-runs entry gates).
- [ ] B11 hallmark green (freshness check aborts and alerts).
- [ ] Sunday digest, Monday re-val, daily exit, freshness check, weekly postmortem, midweek mini all scheduled.
- [ ] Telegram is the only required channel; WhatsApp gracefully optional.
