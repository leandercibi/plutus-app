# 14 — Weekly History: Reports + Outcome Tracking

> Two storage layers per weekly run: PostgreSQL rows (queryable, chartable) and a
> Markdown file at `src/reports/weekly/YYYY-MM-DD.md` (human-readable). The reports
> directory is `.gitignore`d and **the system never auto-commits**.

---

## Two Storage Layers

Every weekly run produces:

1. **PostgreSQL rows** — `weekly_runs` + `recommendations` (with the new `entry_mid`,
   `hold_days_min`, `hold_days_max`, `revalidation_note`, `outcome_*` columns from
   CHANGE_SPEC §4 and §8). Used by the dashboard, Telegram bot, and the outcome
   tracker.
2. **Markdown file** — `src/reports/weekly/YYYY-MM-DD.md`. Single-page summary,
   regenerated at the end of `weekly_pipeline()` and **appended to** by the daily
   outcome tracker once recommendations close.

Both are written at the end of `weekly_pipeline()` in `src/main.py`. See
`12_scheduler.md` for the call site.

> The reports directory is `.gitignore`d. If you want a personal history of reports,
> `git init` `src/reports/` separately on your machine — the system itself does **not**
> stage or commit anything.

---

## Markdown Report Format

Each `src/reports/weekly/YYYY-MM-DD.md` looks like this. New fields per CHANGE_SPEC
are highlighted: `entry_mid`, `hold_days_min`, `hold_days_max`, and an optional
`revalidation_note` block when the Monday revalidation pass downgraded a rec.

```markdown
# Weekly Analysis — 01 June 2026

**Market Regime:** BULLISH
**Strategy Weights:** {"breakout": 0.35, "trend": 0.25, "smc": 0.15, "reversal": 0.15, "composite": 0.10}
**Generated:** 01 Jun 2026 18:47 IST
**Revalidated:** 02 Jun 2026 09:10 IST

---

## BUY Signals (4)

### RELIANCE
- **Confidence:** 8.2/10
- **Entry Zone:** ₹2,375 – ₹2,395 (mid: ₹2,385)
- **Target 1:** ₹2,480 | **Target 2:** ₹2,560
- **Stop Loss:** ₹2,320
- **R:R:** 2.14
- **Hold Days:** 5–10
- **Strategy:** Bundle 3 (Breakout) + Bundle 5 (Composite)
- **Reasoning:** Price broke above 6-week consolidation range (₹2,310–₹2,360) with
  2.8× average volume. RSI at 67 — strong momentum, not overbought. Three large MFs
  increased holdings last month. FII net buyers ₹340Cr this week.
- **Outcome:** PENDING

### TATAMOTORS
- **Confidence:** 7.8/10
- **Entry Zone:** ₹915 – ₹930 (mid: ₹922.5)
- **Target 1:** ₹975 | **Target 2:** ₹1,020
- **Stop Loss:** ₹890
- **R:R:** 1.95
- **Hold Days:** 5–8
- **Strategy:** Bundle 1 (Trend)
- **Revalidation Note:** Downgraded to WATCH on Monday open — gapped +2.6% past entry zone.
- **Outcome:** PENDING

## WATCH (3)

- **WIPRO** — Mixed signals. EMA crossover forming but volume weak. Wait for confirmation.
- **SUNPHARMA** — Reversal setup near Bollinger lower band. RSI 31. Material USFDA hearing next week — high risk.
```

Key rule: **always write the file even if some recommendations failed**. Partial
report > no report.

The `revalidation_note` line is rendered only when `recommendation.revalidation_note`
is non-null (set by the Monday `weekly_revalidate` job — see `12_scheduler.md`).

---

## Outcome Tracking

`track_recommendation_outcomes()` runs Mon-Fri at 16:30 IST and updates
`Recommendation.outcome*` for any PENDING recommendations whose `hold_days_min`
window has elapsed.

### Outcome states

| State | Meaning |
|---|---|
| `PENDING` | Not enough trading days have elapsed yet |
| `HIT_T1` | Price reached Target 1 first |
| `HIT_T2` | Price reached Target 2 first |
| `STOPPED` | Price hit stop loss (or stop + target on the same bar — stop wins) |
| `EXPIRED` | `hold_days_max` elapsed; closed at last close |

### Correctness rules (CHANGE_SPEC §8)

1. **IST trading days, not UTC days.** Use
   `plutus.data.trading_calendar.nse_trading_days_between(start_date, end_date)` which
   counts NSE trading sessions between two IST dates (weekends + NSE holidays
   excluded).
2. **Fill price** is `entry_mid` (mid of the entry zone). Fall back to `entry_high`
   only if `entry_mid` is null. The chosen fill is persisted on
   `recommendation.outcome_fill_price` so the dashboard / audits can reproduce the
   number.
3. **Strictly after the recommendation day:** `df.index.date > created_ist`. The
   recommendation day's bar is excluded — we cannot have entered before the analysis
   was published.
4. **Same-bar collision rule:** if a single daily candle has both
   `High >= target` AND `Low <= stop`, **stop wins** (conservative — daily bars don't
   tell us intraday order, so we book the worse outcome).
5. **Hold-day gates:** skip until `trading_days_elapsed >= hold_days_min` (default 5).
   Mark `EXPIRED` once `trading_days_elapsed >= hold_days_max` (default 10) without a
   target/stop hit.
6. **Persist:** `outcome`, `outcome_fill_price`, `outcome_exit_price`,
   `outcome_exit_date`, `outcome_pct`, `outcome_tracked_at`.
7. `outcome_pct = (outcome_exit_price - outcome_fill_price) / outcome_fill_price * 100`.

### Implementation

```python
# src/plutus/agents/outcome_tracker.py
from datetime import datetime, date
import logging

import pytz

from plutus.config import settings
from plutus.data.ohlcv import fetch_ohlcv
from plutus.data.trading_calendar import nse_trading_days_between
from plutus.db.models import OutcomeVerdict, Recommendation
from plutus.db.session import SessionLocal

log = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def track_recommendation_outcomes() -> int:
    """Update outcome columns for any PENDING recs whose hold_days_min has elapsed.

    Returns the number of recommendations updated this run.
    """
    today_ist = datetime.now(IST).date()
    updated = 0

    with SessionLocal() as db:
        pending = (
            db.query(Recommendation)
            .filter(Recommendation.outcome.in_([None, OutcomeVerdict.PENDING]))
            .all()
        )

        for rec in pending:
            created_ist = rec.created_at.astimezone(IST).date()
            trading_days_elapsed = nse_trading_days_between(created_ist, today_ist)

            hold_min = rec.hold_days_min or settings.HOLD_DAYS_MIN or 5
            hold_max = rec.hold_days_max or settings.HOLD_DAYS_MAX or 10

            if trading_days_elapsed < hold_min:
                continue  # too early to call

            # Pull enough history to cover the hold window plus slack.
            df = fetch_ohlcv(rec.symbol, days=trading_days_elapsed + 5)
            df = df[df.index.date > created_ist]   # strictly AFTER the rec day
            if df.empty:
                continue

            fill = float(rec.entry_mid if rec.entry_mid is not None else rec.entry_high)
            stop = float(rec.stop_loss)
            t1 = float(rec.target1)
            t2 = float(rec.target2) if rec.target2 is not None else None

            outcome: OutcomeVerdict | None = None
            outcome_exit_price: float | None = None
            outcome_exit_date: date | None = None

            for idx, row in df.iterrows():
                hit_t2 = t2 is not None and row.High >= t2
                hit_t1 = row.High >= t1
                hit_stop = row.Low <= stop

                # Conservative same-bar collision rule: stop wins.
                if hit_stop and (hit_t1 or hit_t2):
                    outcome = OutcomeVerdict.STOPPED
                    outcome_exit_price = stop
                elif hit_t2:
                    outcome = OutcomeVerdict.HIT_T2
                    outcome_exit_price = t2
                elif hit_t1:
                    outcome = OutcomeVerdict.HIT_T1
                    outcome_exit_price = t1
                elif hit_stop:
                    outcome = OutcomeVerdict.STOPPED
                    outcome_exit_price = stop

                if outcome is not None:
                    outcome_exit_date = idx.date()
                    break

            if outcome is None:
                if trading_days_elapsed >= hold_max:
                    outcome = OutcomeVerdict.EXPIRED
                    outcome_exit_price = float(df.iloc[-1].Close)
                    outcome_exit_date = df.index[-1].date()
                else:
                    continue   # still inside the hold window

            outcome_pct = (outcome_exit_price - fill) / fill * 100.0

            rec.outcome = outcome
            rec.outcome_fill_price = fill
            rec.outcome_exit_price = outcome_exit_price
            rec.outcome_exit_date = outcome_exit_date
            rec.outcome_pct = outcome_pct
            rec.outcome_tracked_at = datetime.utcnow()
            updated += 1

        db.commit()

    log.info("outcome_tracker: updated %d recommendations", updated)
    return updated
```

### `nse_trading_days_between` helper

`src/plutus/data/trading_calendar.py` exposes `nse_trading_days_between(start, end)`,
which counts weekdays between `start` (exclusive) and `end` (inclusive) minus dates
listed in `src/plutus/data/nse_holidays.txt` (one ISO date per line; refreshed
yearly). If the holiday file is missing, it falls back to "weekdays only" with a
logged warning. Full contract is documented in `04_database.md` / `12_scheduler.md`.

---

## Appending Outcomes to the MD Report

Once the tracker has filled in outcome columns, the same scheduler tick appends a
single "Outcomes (Updated)" section to the original MD file. The section is
rewritten in place each time the tracker runs, so the file always reflects the
current state without growing unbounded.

```python
# src/plutus/agents/outcome_tracker.py (continued)
import os
from pathlib import Path

from plutus.db.models import OutcomeVerdict, Recommendation, WeeklyRun

OUTCOME_HEADER = "## Outcomes (Updated)"
OUTCOME_ICONS = {
    OutcomeVerdict.HIT_T1: "✅",
    OutcomeVerdict.HIT_T2: "🎯",
    OutcomeVerdict.STOPPED: "❌",
    OutcomeVerdict.EXPIRED: "⏰",
}


def update_report_with_outcomes(run_date: date) -> None:
    """Rewrite (or append) the Outcomes section of the weekly MD report."""
    path = Path(settings.REPORTS_DIR) / f"{run_date}.md"
    if not path.exists():
        log.warning("update_report_with_outcomes: %s does not exist", path)
        return

    with SessionLocal() as db:
        run = db.query(WeeklyRun).filter(WeeklyRun.run_date == run_date).first()
        if not run:
            return
        recs = (
            db.query(Recommendation)
            .filter(Recommendation.weekly_run_id == run.id)
            .order_by(Recommendation.confidence.desc())
            .all()
        )

    lines = [f"\n---\n\n{OUTCOME_HEADER}\n"]
    for r in recs:
        if not r.outcome or r.outcome == OutcomeVerdict.PENDING:
            lines.append(f"- {r.symbol}: PENDING\n")
            continue
        icon = OUTCOME_ICONS.get(r.outcome, "?")
        sign = "+" if (r.outcome_pct or 0) >= 0 else ""
        exit_bits = ""
        if r.outcome_exit_date and r.outcome_exit_price is not None:
            exit_bits = (
                f" — exited {r.outcome_exit_date.isoformat()} "
                f"@ ₹{r.outcome_exit_price:.0f}"
            )
        lines.append(
            f"- {r.symbol}: {r.outcome.value} {icon} "
            f"({sign}{(r.outcome_pct or 0):.1f}%){exit_bits}\n"
        )

    body = path.read_text()
    if OUTCOME_HEADER in body:
        # Replace the existing Outcomes section in place.
        head, _ = body.split(OUTCOME_HEADER, 1)
        path.write_text(head.rstrip() + "\n\n---\n\n" + OUTCOME_HEADER + "\n" + "".join(lines[1:]))
    else:
        with path.open("a") as f:
            f.writelines(lines)
```

Example appended block:

```markdown
---

## Outcomes (Updated)
- RELIANCE: HIT_T1 ✅ (+3.6%) — exited 2026-06-04 @ ₹2480
- TATAMOTORS: STOPPED ❌ (-3.5%) — exited 2026-06-03 @ ₹890
- WIPRO: PENDING
- SUNPHARMA: EXPIRED ⏰ (+0.4%) — exited 2026-06-12 @ ₹1605
```

---

## Dashboard History Tab

The History tab in `src/dashboard.py` (Tab 7 — see `11_dashboard.md`) renders:

1. **Top-level table** — every row in `weekly_runs`, sortable by date, showing
   `run_date`, `market_regime`, `total_buy_signals`, `total_watch_signals`, the
   number of closed recommendations so far, and a "Win % so far" column computed as
   `(HIT_T1 + HIT_T2) / closed * 100`.
2. **Filter dropdowns** — by quarter (`YYYY-Qn`) or month (`YYYY-MM`).
3. **Drill-down** — clicking a row expands into:
   - The markdown body of `src/reports/weekly/<date>.md` (if present on disk).
   - A recommendations table for that run (entry mid, T1, stop, outcome, P&L %, exit
     date).
   - An **outcomes summary card** with HIT_T1, HIT_T2, STOPPED, EXPIRED, PENDING
     counts plus the aggregate average P&L %.
   - An **equity curve** — cumulative `outcome_pct` across all closed recs from that
     run, ordered by `outcome_exit_date`.

The drill-down view is implemented by `_render_history_drilldown()` in
`11_dashboard.md` and queries `_outcome_stats_for_run(run_id)`. Outcome
state for the card maps directly to the columns the tracker populates above
(`outcome`, `outcome_pct`, `outcome_exit_date`).

```python
# Outcome-stats query used by the History tab
from sqlalchemy import func

with SessionLocal() as db:
    rows = (
        db.query(Recommendation.outcome, func.count(Recommendation.id))
        .filter(Recommendation.weekly_run_id == run_id)
        .group_by(Recommendation.outcome)
        .all()
    )
```

---

## Telegram `/history` Command

```
/history                → lists the 5 most recent weekly report dates
/history 2026-05-25     → returns that week's MD report
```

Telegram messages have a 4096-character limit. The handler checks the file size
first; if the body fits, it's sent verbatim. Otherwise the bot replies with a
summary built from the same MD file:

- The first 4 BUY/WATCH bullets (symbol + one-line reasoning).
- Outcome counts: HIT_T1 / HIT_T2 / STOPPED / EXPIRED / PENDING.
- A note pointing the user to the dashboard's History tab for the full report.

```python
# src/plutus/alerts/telegram_bot.py — /history handler
TELEGRAM_LIMIT = 4096

async def cmd_history(update, context):
    args = context.args
    if not args:
        # List the 5 most recent runs.
        with SessionLocal() as db:
            runs = (
                db.query(WeeklyRun)
                .order_by(WeeklyRun.run_date.desc())
                .limit(5)
                .all()
            )
        msg = "Recent weekly reports:\n" + "\n".join(
            f"• /history {r.run_date}" for r in runs
        )
        await update.message.reply_text(msg)
        return

    run_date = args[0]
    path = Path(settings.REPORTS_DIR) / f"{run_date}.md"
    if not path.exists():
        await update.message.reply_text(f"No report for {run_date}.")
        return

    body = path.read_text()
    if len(body) <= TELEGRAM_LIMIT:
        await update.message.reply_text(body)
        return

    summary = _summarise_report(body, run_date)
    await update.message.reply_text(summary)


def _summarise_report(body: str, run_date: str) -> str:
    """Summarise a too-long MD report into <=4096 chars for Telegram."""
    bullets: list[str] = []
    in_buy_or_watch = False
    for line in body.splitlines():
        if line.startswith("## BUY") or line.startswith("## WATCH"):
            in_buy_or_watch = True
            continue
        if line.startswith("## ") and not line.startswith("## Outcomes"):
            in_buy_or_watch = False
        if in_buy_or_watch and line.startswith("- "):
            bullets.append(line)
        if len(bullets) >= 4:
            break

    counts = {k: 0 for k in ("HIT_T1", "HIT_T2", "STOPPED", "EXPIRED", "PENDING")}
    for line in body.splitlines():
        for k in counts:
            if k in line:
                counts[k] += 1
                break

    parts = [f"📋 Weekly report — {run_date} (truncated)"]
    if bullets:
        parts.append("\nTop picks:")
        parts.extend(bullets[:4])
    parts.append(
        "\nOutcomes: "
        f"✅ {counts['HIT_T1']} · 🎯 {counts['HIT_T2']} · "
        f"❌ {counts['STOPPED']} · ⏰ {counts['EXPIRED']} · "
        f"⏳ {counts['PENDING']}"
    )
    parts.append("\nFull report → dashboard › History tab.")
    return "\n".join(parts)[:TELEGRAM_LIMIT]
```

---

## Reports Directory Note

`src/reports/weekly/` is `.gitignore`d. The system never auto-stages or
auto-commits these files. If you want a private history on your own machine, run
`git init src/reports/` once and commit on your own cadence; nothing in the
pipeline depends on that.

---

## Cross-references

- `04_database.md` — `recommendations` schema (`entry_mid`, `hold_days_min`,
  `hold_days_max`, `outcome_*`, `revalidation_note`).
- `08_agents.md` — synthesizer prompt that emits `hold_days_min` / `hold_days_max`.
- `11_dashboard.md` — History tab UI and helpers (`_render_history_drilldown`,
  `_outcome_stats_for_run`).
- `12_scheduler.md` — schedules `weekly_pipeline` (Sun 18:00),
  `weekly_revalidate` (Mon 09:10) and `outcome_tracker` (Mon-Fri 16:30).
