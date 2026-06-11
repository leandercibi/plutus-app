# 14 — Dashboard

> Streamlit. One app, multiple windows (sidebar items). Calm layout per the user's reference mockup. Each window owns one job; v2-distinctive features sit on the right window, not the home view. Implements B17 (pillar bars, counterfactual, calibration badge, soft dead-zone), B15 (cash banner), B10 surface (real fill entry), exposes outputs from all upstream specs.

The Home view is documented as a wireframe-in-words (per user choice for option b). The other windows likewise — the build agent renders them from these descriptions.

---

## 1. Module layout

```
src/plutus/dashboard/
├── app.py                  # streamlit entry
├── nav.py                  # sidebar
├── theme.py                # dark theme constants
├── windows/
│   ├── home.py
│   ├── user_flow.py
│   ├── signals.py
│   ├── positions.py
│   ├── candidates.py
│   ├── tranches.py
│   ├── settings.py
│   ├── postmortem.py
│   ├── calibration.py
│   └── strategy_lab.py
└── components/
    ├── pillar_bar.py
    ├── calibration_badge.py
    ├── counterfactual.py
    ├── regime_banner.py
    ├── cash_banner.py
    ├── tranche_pills.py
    ├── score_chip.py
    └── benchmarks_strip.py
```

---

## 2. Theme

Dark surface, calm palette:
- bg primary `#1a1a1a`, surface `#1f1f1d`, panel `#232321`, border `#2a2a28`
- text primary `#f5f5f3`, secondary `#a5a5a1`, tertiary `#7a7a76`
- swing accent `#c69a4a` (amber), accumulation accent `#8a7be0` (purple), cash `#7fc88a` (green), regime bear `#c45a5a`
- Numbers always rounded (₹ comma-grouped; pct one decimal).
- Sentence case throughout.
- No drop shadows, no gradients.

---

## 3. Sidebar

Three sections + configure (per the reference mockup the user supplied):

```
overview        Home, User flow
swing           Signals (badge: current regime), Positions
accumulation    Candidates (badge: count), Tranches
configure       Settings
postmortem      Postmortem, Calibration, Strategy lab
```

The active item carries a left amber/purple accent line depending on which domain it belongs to.

---

## 4. Window: Home

Layout (top → bottom):

1. **Header row**: title "Portfolio overview" · regime pill (e.g., "● Nifty BEAR · −2.47% below EMA50") · total capital figure.
2. **Four metric cards** (one row, equal width): total capital, swing allocated, accumulation allocated, cash reserve. Each shows headline number + one-line subtitle.
3. **Allocation bar** (single 6px-tall strip in three colors swing/accumulation/cash) with legend.
4. **Regime advisory banner** (red-tinted left-border block): prose explaining current regime stance. Includes the cash-as-position rule wording (B15) when active. Includes the "swing paused / unlocked" status.
5. **Two-column panel**: left = Swing mode (status pill: Active / Paused), right = Accumulation mode (status pill). Each lists 3–5 names with a small horizontal bar + score + status pill (HOLD/BUY/WATCH for swing; tranche pills 1·2·3 for accumulation) + per-row second line with `E +0.18R · n=42 · med` for swing or `RS 30/90/180: 68/72/74 · thesis-state` for accumulation.
6. **Bottom-right "View all" link** under each panel.

Strict: no pillar decomposition bars on this page. No counterfactual prose. No benchmark strip. Those live on Signals / Postmortem.

---

## 5. Window: Signals (swing detail)

For each signal:
- Score chip (e.g., `BUY · 76`) + calibration badge (`n=84 · high`).
- Entry / SL / T1 / T2 row.
- **Pillar decomposition bars** (Technical, Expectancy, Flow, Sentiment, Regime fit, Fundamentals) using `pillar_bar.py`.
- **Chip strip**: delivery %, ADV use, circuit hits in 90d, earnings in window, sector heat.
- **Counterfactual line** (`counterfactual.py`): "stays BUY unless regime flips or entry slips above ₹X" / "upgrades to BUY if entry < ₹X or delivery > 50%".
- Buttons: open detail, send to Telegram (re-send), log real fill (B10).

Filters at top: regime, bundle, label, calibration band.

---

## 6. Window: Positions (swing open + recent)

For each open position:
- Symbol, bundle, age (days since entry), risk in R.
- Current realized R, MFE so far, time-elapsed-to-T1 progress bar (drives no-progress visibility).
- Trailing stop value (if past T1).
- Buttons: log real fill (B10), manual exit.

For recent closed (last 14 days): realized R, exit reason, mock-vs-real slippage delta if both fills present.

---

## 7. Window: Candidates (accumulation)

For each candidate:
- Symbol, label (ACCUMULATE_NOW / BUILD_SLOWLY / WATCH / AVOID).
- Pillar decomposition (Quality, Growth, Valuation-capped, RS-blend).
- RS 30/90/180 small bars.
- CAGR EPS (3y, 5y) + valuation cap indicator.
- Hard-avoid badges (red) when present.

---

## 8. Window: Tranches

For each position:
- Tranche-pill row (1·2·3·4·5; filled vs empty using `tranche_pills.py`).
- Avg cost, current pct gain/loss.
- Last thesis check date + result.
- Paused-flag with reason when applicable.
- Buttons: pause / resume / convert to swing (bull-ready).

---

## 9. Window: Postmortem

- Weekly date selector.
- **Benchmarks strip** (`benchmarks_strip.py`) — Plutus swing, Nifty B&H, regime-switched, random-liquid; all net of costs.
- Per-bundle pull-throughs.
- WRONG_DIRECTION count, no-progress scratch count.
- Slippage-divergence section (mock vs real, B10).
- Calibration table with CIs (every win-rate has a CI column; no naked win rates — C5).

---

## 10. Window: Calibration

- Per (bucket, regime) row: n_closed, expectancy, CI, confidence band, SPRT state.
- Tuner proposals (A14): for each, show old / proposed / Δexpectancy / family-corrected p. Apply button disabled unless `auto_tune_enabled` is False AND user has manual-approval rights.
- Dated history of applied changes with revert button.

---

## 11. Window: Strategy Lab

- Bundle selector + symbol selector.
- Backtest config (start, end, cost model on/off, fill policy on/off).
- Run button → equity curve + benchmark strip + bundle stats.
- SMC bundle (C3) shown here as display-only with explicit "not in live seeding" badge.

---

## 12. Window: User flow

- A diagram (rendered SVG) of the weekly cycle: Sun full run → Mon 09:10 re-val → daily exit ticks → Sun postmortem.
- Latest run log table from `run_log.py`.
- Freshness assertion status indicator (B11).

---

## 13. Window: Settings

- Read-only view of all `Settings` fields.
- Editable subset (risk pct, max concurrent, midweek mini toggle).
- Reason field required on save (logged).

---

## 14. Components (public API)

```python
def pillar_bar(label: str, value: int, max_value: int, color_token: str) -> None
def calibration_badge(n: int, band: Literal["low", "medium", "high"]) -> None
def counterfactual(text: str) -> None
def regime_banner(verdict: RegimeVerdict, cash_decision: CashDecision | None) -> None
def cash_banner(decision: CashDecision) -> None
def tranche_pills(seqs_filled: list[int], total: int = 5) -> None
def score_chip(label: str, score: int) -> None
def benchmarks_strip(result: BenchmarkResult) -> None
```

Each component is a Streamlit function with no return value; renders into the current container.

---

## 15. Tests (`tests/dashboard/`)

Streamlit testing is done via the official `streamlit.testing.v1.AppTest`.

| Test file | Cases |
|---|---|
| `test_app_boots.py` | App starts; no exception; sidebar renders all expected items. |
| `test_home_metric_cards_render.py` | Four cards with correct numbers from fixture session. |
| `test_home_regime_banner_text.py` | Banner string matches `CashAsPosition.decide(...).reason` when applicable. |
| `test_home_two_panels.py` | Both Swing and Accumulation panels render with 3-5 rows each. |
| `test_signals_pillar_bars_present.py` | Six pillar bars on a signal detail. |
| `test_signals_calibration_badge.py` | Badge band reflects the underlying calibration row's `confidence_band`. |
| `test_signals_dead_zone_shows_buy_watch.py` | (B17 hallmark) Score 70 renders as BUY_WATCH chip in the dead-zone color. |
| `test_signals_counterfactual_text.py` | Counterfactual present and non-empty for any signal. |
| `test_positions_real_fill_post.py` | Submitting the form posts to `/swing/trades/{id}/fills/real`. |
| `test_candidates_render.py` | Hard-avoid badges visible when set. |
| `test_tranches_pause_button.py` | Pause action transitions position state. |
| `test_postmortem_three_benchmarks.py` | (B2 hallmark) All four numbers in the strip; net of costs. |
| `test_postmortem_no_naked_win_rate.py` | (C5 hallmark) Every win-rate cell has an adjacent CI cell. |
| `test_calibration_tuner_apply_disabled_when_auto_tune.py` | When `auto_tune_enabled=True`, manual apply button is disabled. |
| `test_strategy_lab_smc_display_only.py` | (C3) SMC bundle shows the "not in live seeding" badge. |
| `test_user_flow_freshness_indicator.py` | Stale fixture → indicator red. |
| `test_settings_save_requires_reason.py` | Empty reason → save disabled. |

---

## 16. Acceptance criteria

- [ ] All windows render against a fixture session DB.
- [ ] Hallmark tests pass (B17, B2, C5, C3).
- [ ] Sidebar matches the user's reference structure.
- [ ] Home view contains no pillar bars / counterfactual / benchmark strip (those live on detail pages).
- [ ] Components in §14 used everywhere instead of one-off code.
- [ ] Theme constants centralized in `theme.py`; no inline hex outside that file (lint rule).
