# GLOSSARY

> Definitions used across the v2 spec set. Cross-references point to the doc that owns the concept.

---

**Accumulation domain.** The patient-capital side of Plutus: multi-month tranche-based positions selected by fundamentals + RS-blend, exited on thesis invalidation. Owned by `08_accumulation_domain.md`.

**ADV (Average Daily Volume).** 20-day average traded quantity. Used to cap position size (B5). Owned by `06_shared_regime_and_risk.md`.

**ATR (Average True Range).** Volatility measure. Used in stop placement, no-progress thresholds, tranche-trigger normalization (A13). Owned by `07_swing_domain.md`.

**ATR-normalized trigger.** Tranche-step prices defined as multiples of ATR rather than fixed −8 / −15%. Same conviction structure across FMCG (low ATR) and small-cap (high ATR). Owned by `08_accumulation_domain.md`.

**BUY-watch.** Soft dead-zone label for scores 67–73 inclusive (B17). Distinct from BUY and WATCH. Owned by `07_swing_domain.md`, `11_calibration_and_tuning.md`.

**Bull-ready.** The voluntary conversion path from accumulation to swing when regime flips BULL with breadth-confirmed. Capital is not force-migrated. Owned by `08_accumulation_domain.md`.

**Bundle.** A swing entry strategy with its own setup detection, stop, T1, T2. Trend, Breakout, Reversal, VCP, Composite, PEAD, SMC. Owned by `07_swing_domain.md`.

**Calibration band.** `low` (n<20), `medium` (n<50), `high` (n>=50). Drives the badge on the dashboard (B17). Owned by `11_calibration_and_tuning.md`.

**Cash-as-position.** Rule: when fewer than `cash_position_min_deploy_count` qualifying signals exist, undeployed capital stays in cash by rule, not deployed into mediocrity (B15). Owned by `06_shared_regime_and_risk.md`.

**Circuit filter.** Daily price-move band on NSE (5/10/20%). Stocks locked at the band have truncated price action that corrupts VCP and breakout detection (B7). Owned by `07_swing_domain.md`.

**Corroboration.** A8 rule: a sentiment hard-kill must be backed by ≥2 entity-resolved headlines, or one headline + price/volume confirmation, or a structurally verifiable event. Uncorroborated → graded penalty, not kill. Owned by `09_sentiment_and_smart_money.md`.

**Cost model.** STT, brokerage, exchange charges, GST, stamp duty + slippage scaling with position/ADV and ATR. Applied in backtest and live (B1). Owned by `05_cost_and_fill_model.md`.

**Counterfactual.** The nearest single-input change that would flip a signal's label (e.g., "stays BUY unless entry slips above ₹X"). Shown on signal detail (B17). Owned by `07_swing_domain.md` (computation) and `14_dashboard.md` (display).

**Delivery %.** NSE-published delivery quantity / total traded quantity per stock per day, 1-day-lagged. Used to filter out block-deal noise from the volume confirmation gate (A9). Owned by `04_data_pipeline.md`, `09_sentiment_and_smart_money.md`.

**Delivery-adjusted volume.** `traded_qty * delivery_pct`. Replaces raw volume in the swing confirmation gate (A9, C4). Owned by `07_swing_domain.md`.

**Drawdown governor.** Per-trade risk halves when pool draws down ≥ trigger (default 7%) from high-water mark; restores after 3-day recovery above trigger (B4). Owned by `06_shared_regime_and_risk.md`.

**Expectancy (R).** `E = P(T1)*R_T1 + P(T2)*R_T2 - P(SL)*R_SL` with pooled per-regime hit rates and net of costs (A4). The primary swing entry gate. Owned by `07_swing_domain.md`.

**FII / DII.** Foreign / Domestic Institutional Investor net flows. v2 lives in the Regime pillar (A7), not per-stock. Owned by `06_shared_regime_and_risk.md`.

**Fill policy.** Backtest fill rules: entries at next-bar open + slippage; stops at the worse of (stop price, next-bar open); targets at intra-bar touch or gap-through (A1). Owned by `05_cost_and_fill_model.md`.

**Freshness assertion.** B11 rule: the latest candle date must equal the last NSE trading day before any signal publishes; else the run aborts. Owned by `04_data_pipeline.md`, `13_alerts_and_scheduler.md`.

**Hallmark test.** A single test that, if green, evidences a specific review item is fixed; if red, the fix has regressed. Listed in `TESTING.md` §9.

**Hard-avoid.** Conditions that force an AVOID label regardless of pillar score: D/E breach (accumulation), corroborated sentiment kill (swing), expectancy_R < 0 (swing). Owned by `07_swing_domain.md`, `08_accumulation_domain.md`.

**LLM color.** Text-only narrative output from the LLM for display. By rule, may not enter any classification gate (A8/C6). Owned by `09_sentiment_and_smart_money.md`.

**MFE / MAE.** Maximum Favorable / Adverse Excursion during a trade's life. Used to parameterize trailing exits (B8) and stop tuning (E3). Owned by `07_swing_domain.md`.

**Monday re-validation.** A15: at 09:10 IST Monday, re-runs entry gates against Monday's open and weekend news for each Sunday-generated signal. Kept / killed alerts sent. Owned by `07_swing_domain.md`, `13_alerts_and_scheduler.md`.

**No-progress exit.** B8 unified rule: if realized R toward T1 < threshold by elapsed-pct of hold window >= threshold, exit at market. Subsumes the early-window and midpoint variants. Owned by `07_swing_domain.md`.

**OOS (Out-of-sample).** The held-out window in walk-forward. Bundle selection uses pooled OOS per-regime shrunk Sharpe (A2). Owned by `10_backtesting_and_benchmarks.md`.

**Per-regime stat store.** B14: persistent table of bundle stats keyed by `(bundle, regime, as_of_date)`. Read by the selector. Owned by `10_backtesting_and_benchmarks.md`.

**PIT universe (Point-in-time).** A17: universe membership as of a historical date for backtests, frozen at that date — no survivorship bias. Owned by `04_data_pipeline.md`.

**Pillar.** A scoring component in the swing rubric (Technical, Expectancy, Flow, Regime fit, Fundamentals, Sentiment) or accumulation rubric (Quality, Growth, Valuation-capped, RS). Owned by `07_swing_domain.md` and `08_accumulation_domain.md`.

**Regime.** Market state: BULL / SIDEWAYS / BEAR. Derived from Nifty trend + breadth + India VIX + FII/DII (B13). Owned by `06_shared_regime_and_risk.md`.

**Regime-switched baseline.** "Long Nifty when BULL; cash otherwise." Tests the regime detector's value independently of stock-picking (B2). Owned by `10_backtesting_and_benchmarks.md`.

**RS (Relative Strength).** Stock return minus index return. v2 blends 30/90/180-day with heavier weight on longer horizons (A12). Owned by `08_accumulation_domain.md`.

**Shrunk Sharpe.** Sharpe ratio shrunk toward a cross-bundle prior proportional to trade count, to dampen lucky small-sample Sharpes (A2). Owned by `10_backtesting_and_benchmarks.md`.

**SMC (Smart Money Concepts).** A swing bundle. In v2, gated to display-only until pooled OOS evidence justifies it (C3). Owned by `07_swing_domain.md`.

**Soft dead-zone.** Scores 67–73 rendered as BUY-watch, not BUY, until calibration is dense enough to distinguish (B17). Owned by `11_calibration_and_tuning.md`.

**SPRT (Sequential Probability Ratio Test).** Sequential hypothesis test that decides accept-H0 / accept-H1 / continue as samples arrive. Drives the tuner's "act / wait" decision (A14). Owned by `11_calibration_and_tuning.md`.

**Swing domain.** The day-to-week trading side of Plutus. Owned by `07_swing_domain.md`.

**Tranche.** One of typically 5 entries that build an accumulation position. Triggered by ATR-normalized price drops with thesis re-validation before each fill (A13). Owned by `08_accumulation_domain.md`.

**VCP (Volatility Contraction Pattern).** Minervini-style swing setup: multiple price contractions of decreasing amplitude on declining volume, ending in a breakout. Owned by `07_swing_domain.md`.

**Walk-forward.** Backtest evaluation that slides a (train, OOS) window through history, avoiding in-sample contamination of OOS stats (A2). Owned by `10_backtesting_and_benchmarks.md`.
