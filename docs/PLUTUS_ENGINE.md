# Plutus — The Engine

A field guide for traders. Explains what the system does, why it does it that way, and where the edge is supposed to come from.

No code. No file paths. Trading concepts only.

---

## 1. What Plutus is

Plutus is a personal trading research engine for the Indian equities market (NSE cash). It does three things:

1. **Screens.** It scans a universe of liquid stocks every Sunday and produces a short list of candidates ranked by a deterministic score.
2. **Recommends.** For each top candidate, it produces a structured trade plan — entry zone, stop loss, two targets, position size, hold window, and a short thesis.
3. **Watches.** Once you place a trade (mock or real, your choice), it monitors live prices during market hours and alerts you on Telegram when something actionable happens — stop-loss approaches, targets get hit, the trend invalidates.

It runs in two modes that coexist:

- **Swing mode** — momentum trades held 3–10 days. Active in bullish and sideways markets. Quiet during bears.
- **Accumulation mode** — patient capital tranched into fundamentally strong stocks over weeks. Active in bear and sideways markets. Hands off during raging bulls because the swing engine catches those better.

You allocate capital between the two. They never share budget.

---

## 2. The trading philosophy

A swing trade and an accumulation buy look the same on the screen — both are "buy stock". But they are different *instruments* used in different conditions. Plutus refuses to mix them.

| | Swing trade | Accumulation buy |
|---|---|---|
| Question it answers | Will this stock outperform over the next 1–2 weeks? | Will this stock be much higher 6–12 months from now? |
| Signal source | Chart pattern + momentum + flows | Fundamentals + relative strength + institutional accumulation |
| Stop loss | 1.5× ATR — tight | Wide or staggered tranches; rarely a single hard SL |
| Hold | 3–10 trading days | 3–18 months, often through drawdowns |
| Market regime | Bull / sideways only | Bear / sideways preferred |
| Position sizing | Risk-cap based (% of swing pool, ATR-anchored) | Tranche-based (⅓ + ⅓ + ⅓ across drawdowns) |

The reason both exist: during a bear market, the swing engine correctly steps aside (it cannot find favourable R:R with the index below its 50-day EMA). The accumulator picks up the slack — that's when the best long-term entries appear. When the index recovers, the swing engine takes over. The user is never left with "do nothing" as the only option.

---

## 3. Data sources

Plutus is opinionated about data. Free sources are preferred. Anything that requires a paid feed is justified explicitly.

### Market data (OHLCV — open/high/low/close/volume)

Three providers, used in order:

1. **AngelOne SmartAPI** — primary. Real-time + historical daily candles. Throttled to 2.5 requests/second (well under the 3/sec rate cap) with a 170-call/minute window (10 below the 180 ceiling).
2. **Jugaad-data** — fallback. Scrapes BSE/NSE historical data. Slower, but doesn't require auth.
3. **Yahoo Finance (yfinance)** — last resort. Used when the first two are down. Symbols are mapped (e.g. RELIANCE → RELIANCE.NS).

Every fetch is cached on disk for one trading day. A weekly run hits the network roughly once per stock; intraday checks pull only live last-traded-price (LTP).

### Index data

Nifty 50, Bank Nifty, and 12 sector indices (IT, Auto, Pharma, FMCG, Metal, Realty, Energy, Infra, PSE, Media, plus Bank Nifty) — pulled via the same OHLCV pipeline. Used by the regime detector and the relative-strength calculator.

### Institutional flow

- **FII/DII** — daily net cash provisional figures, pulled from the NSE public API. Market-wide, not per stock.
- **Mutual fund accumulation** — per-stock holdings deltas, scraped from Tickertape. Verdict comes back as `ACCUMULATING`, `REDUCING`, `NEUTRAL`, or `UNKNOWN`.

### News and sentiment

- News headlines for each top-20 candidate, pulled from a NewsAPI feed.
- Headlines are filtered against a tiered keyword list (`tier_A` for material events like earnings, dividends, debt downgrades; `tier_B` for softer signals like analyst upgrades; a stoplist for noise like "rumour" or "speculation").
- Each headline gets a sentiment score (−5 to +5). A material event with a sufficiently negative score becomes a *hard avoid* — the trade is killed regardless of how good the chart looks.

### Fundamentals (Accumulation mode only)

- **P/E ratio, debt-to-equity, EPS growth** — fetched from yfinance per stock (free for NSE tickers).
- **Sector classification** — Tickertape (cached 24 h).
- **Beta vs Nifty** — Tickertape or computed locally from OHLCV history.
- **MF holdings delta** — same Tickertape signal used by the swing smart-money pillar.

### What we deliberately *don't* use

- **Reddit / Twitter sentiment** — too noisy, too slow to clean, the time-to-insight isn't worth the API maintenance.
- **Real-time options chain** — out of scope; we do equities-only.
- **Paid premium feeds (Bloomberg, Reuters, Trendlyne paid tier)** — the marginal accuracy doesn't justify the cost for a personal-capital tool.

---

## 4. The technical indicators

These are pre-computed once per OHLCV fetch and read by every strategy bundle and the scoring rubric. No bundle recomputes them.

| Indicator | What it measures | Where used |
|---|---|---|
| **EMA 20, 50, 200** | Short, medium, long-term trend | Trend alignment (scoring), Trend bundle entry |
| **RSI(14)** | Momentum oscillator, 0–100 | Reversal bundle entries, scoring momentum sub-component |
| **MACD (12, 26, 9)** | Trend change + momentum impulse | Scoring momentum, Trend bundle filter |
| **MACD histogram direction** | Acceleration of MACD | Scoring momentum sub-score |
| **ATR(14)** | Average true range — typical daily move in absolute ₹ | Stop loss, target, position sizing — anchors everything |
| **Volume MA(20)** | Average 20-day volume | Baseline for volume confirmation |
| **Volume ratio** | Today's volume ÷ 20-day MA | Setup confirmation in every bundle (≥1.3× required) |
| **Donchian channel (20)** | Highest high / lowest low of last 20 bars | Breakout bundle entries |
| **Swing high/low (5-bar pivots)** | Local price extremes | SMC bundle structure detection |

ATR is the single most important number in the system. It is what lets the same risk rule (2% of swing pool per trade) produce *very different* position sizes across volatile vs calm stocks. A stock with ATR ₹30 will get a smaller position than one with ATR ₹8, even at the same price.

---

## 5. The swing strategy bundles

Seven strategy "bundles" run in parallel on every top candidate. Each bundle is one specific way of looking at the chart. The bundles do not vote — they each independently produce a backtest result (Sharpe, win rate, trade count over the last 90 days). The bundle with the highest validated Sharpe seeds the trade plan; the rest are surfaced as supporting context.

### Trend bundle

**Idea:** Buy strength in an uptrend. Add when momentum reaccelerates.

**Entry rule:** EMA 20 > EMA 50 > EMA 200 (stacked bullish) AND today's close > EMA 20 AND today's MACD histogram is rising AND volume ratio ≥ 1.3.

**Regime gate:** Only triggers when Nifty is in BULL regime. In SIDEWAYS, the bundle is weighted down. In BEAR, it does not fire.

**Stop / target:** Stop = entry − 1.5 × ATR. T1 = entry + 2 × ATR. T2 = entry + 3 × ATR.

**Best at catching:** Continuation moves in trending stocks. Loses in chop and reversals.

### Reversal bundle

**Idea:** Buy oversold stocks at the bottom of their range when momentum starts turning.

**Entry rule:** RSI dipped below 30 within the last 5 bars AND has crossed back above 35 AND today's close > yesterday's high AND volume ratio ≥ 1.3 AND price is above the 200-day EMA (long-term trend still up).

**Regime gate:** Best in SIDEWAYS / range-bound markets. Weighted up there, weighted down in strong trends.

**Stop / target:** Stop = recent swing low − 0.5 × ATR. Targets at the midpoint and top of the recent range.

**Best at catching:** Pullbacks in healthy uptrends. Bad at catching the bottom of a real bear leg — the regime gate prevents that.

### Breakout bundle

**Idea:** Buy stocks that have made new 20-day highs on strong volume after consolidating.

**Entry rule:** Today's close > 20-bar Donchian high AND volume ratio ≥ 1.5 (stricter than the others) AND the prior 10 bars showed contraction (ATR shrinking) AND sector relative strength is in the top 3 of all sectors.

**Regime gate:** Active in BULL only. Sector RS gate prevents false breakouts in laggard sectors during regime confusion.

**Stop / target:** Stop = entry − 2 × ATR (wider, because breakouts often retest). T1 = entry + 3 × ATR. T2 = entry + 5 × ATR.

**Best at catching:** Early-stage trends. Vulnerable to whipsaws if the volume confirmation is weak.

### SMC bundle (Smart Money Concepts)

**Idea:** Read institutional footprints from structure — Break of Structure (BOS) and Change of Character (CHOCH) on N-bar swing highs and lows.

**Entry rule:** Recent BOS (price made a new higher high after a prior lower high) AND the pullback into the previous order block (the consolidation zone before the impulse) held AND a CHOCH on the lower timeframe confirmed bullish re-engagement.

**Regime gate:** Active in BULL and SIDEWAYS. Demoted to "experimental" weight until walk-forward proves it OOS.

**Stop / target:** Stop = below the order-block low. Targets at the next BOS level above.

**Best at catching:** Clean structural reversals around institutional levels. Misleading in low-volume names where structure is noisy.

### Composite bundle

**Idea:** Ensemble. Take the Trend + Reversal + Breakout entry signals and weight them by recent bundle performance.

**Entry rule:** At least 2 of the 3 sub-bundles agree on direction AND the weighted signal is above threshold.

**Regime gate:** Inherits gates from sub-bundles.

**Stop / target:** Conservative — the tightest of the three sub-bundle stops; the closest of the three targets.

**Best at catching:** High-conviction setups where multiple lenses agree. Lower trade frequency but higher win rate by design.

### VCP bundle (Volatility Contraction Pattern)

Minervini's classic. Pioneered for US midcaps; works in NSE midcaps with tuning.

**Idea:** Stocks that are about to break out compress in a series of progressively smaller pullbacks before launching.

**Entry rule:** Detect 3+ consecutive pullbacks where each successive ATR-corrected drawdown is smaller than the previous one (each contraction tightens) AND the stock is trading in the 50–70 RSI zone (constructive momentum, not overbought) AND on the breakout bar, volume ≥ 1.5× 20-day MA AND sector RS is top 3.

**Regime gate:** BULL only. Universe prefilter: market cap LARGE or MID; small-caps too noisy.

**Stop / target:** Stop = pivot low − 0.5 × ATR. T1 = +2 × ATR. T2 = +4 × ATR.

**Best at catching:** Stage-2 uptrends after long bases. Misses if the consolidation isn't clean.

### PEAD bundle (Post-Earnings Announcement Drift)

A market-microstructure anomaly: stocks that gap up hard on earnings tend to drift higher for several days.

**Entry rule:** Earnings-day gap up > 5% on volume ≥ 2× 20-day MA AND entry on the first pullback to either the gap-fill price or the 5/10 EMA — whichever comes first within 3 trading days.

**Regime gate:** Active around Indian earnings windows (Jul / Oct / Jan / Apr). Quiet outside.

**Stop / target:** Stop = gap-fill price (defines the failure case — if the gap fills, the signal is dead). Hold 3–15 trading days. T1 = +1 × initial gap size. T2 = +2 × gap size.

**Best at catching:** Surprise upside earnings beats. Requires the earnings-date data to be accurate; mis-tagged dates kill it.

---

## 6. The swing scoring rubric

Once the bundles have run, every top candidate is scored on a deterministic 0–100 rubric. **The score is not produced by an LLM.** It is pure arithmetic. The LLM writes the prose thesis later; it does not vote on the recommendation.

The composite score is a weighted sum of five **pillars**:

| Pillar | Weight | What it measures |
|---|---|---|
| Technical | 40% | EMA stack alignment, RSI position, MACD direction, volume confirmation, best-bundle Sharpe |
| Smart Money | 15% | FII/DII net flow direction, MF accumulation verdict |
| Sentiment | 15% | News sentiment score, hard avoid on material negative events |
| Regime | 15% | Nifty trend + slope, sector relative strength rank |
| Risk/Reward | 15% | ATR-anchored R:R; ramps from 1.5× (floor) to 2.5× (full credit) |

Each pillar produces a 0–100 number. The composite is the weighted sum, rounded to integer.

### How pillars actually score

- **Technical** breaks down further into: trend alignment (30%), momentum / RSI (25%), volume confirmation (15%), MACD signal (15%), best-bundle backtest Sharpe (15%). A stock with EMA 20 > 50 > 200, RSI 65, MACD rising, volume 1.7× MA, and best bundle Sharpe 1.8 will land near the top of this pillar.

- **Smart Money** combines institutional flow (60% of the pillar) with MF accumulation (40%). Both FII and DII net-buying gives the maximum institutional sub-score. MF status `ACCUMULATING` gives the max MF sub-score. Neither paid feed; both free.

- **Sentiment** is a linear map of the raw sentiment score (-5 to +5 → 0 to 100), capped at 85 if there is *any* material event (good news still adds volatility risk). A material event with negative polarity returns 0 *and* adds `material_negative_event` to a hard-avoid list.

- **Regime** combines Nifty status (60% of the pillar — BULL with strong slope = ~100, BEAR = ~10, SIDEWAYS = 50) with sector relative-strength rank (40%) — top-3 sector = 100, bottom-3 = 0.

- **Risk/Reward** floor is 1.5×. Below that, the score is 0 — which kills BUY classifications because BUY also requires R:R > 0. Linear ramp from 1.5× (score 0) to 2.5× (score 100).

### Classification

The composite + a few hard rules produce one of four classifications:

- **BUY** — composite ≥ 70 AND R:R > 0 AND position size > 0 AND no material negative AND regime ≠ BEAR.
- **WATCH** — composite 55–69 OR (composite ≥ WATCH threshold AND regime = BEAR — the bear regime downgrades BUY to WATCH at best).
- **HOLD** — composite 35–54.
- **AVOID** — composite < 35 OR material negative event present OR hard-avoid flag set.

This is deliberately rigid. The number does the deciding, not the narrative. The LLM-written thesis is a *report* on the decision, not the decision itself.

### Why this design

Earlier iterations had the LLM produce the recommendation. Two failure modes appeared:

1. The LLM defaulted to "WATCH" as the safe answer whenever the inputs disagreed, leading to dashboards full of mid-grade non-actionable signals.
2. The score was not back-testable. We could not ask "did score 6.5 win more than score 4.5?" because the LLM's output was textual and inconsistent.

The deterministic rubric fixes both: every decision is reproducible from the inputs, and we can bucket by score and measure realised win rate empirically.

---

## 7. The accumulation scoring rubric

Accumulation uses a different rubric because the question is different. The score is also 0–100, but the pillars and weights are different.

| Pillar | Weight | What it measures |
|---|---|---|
| Fundamental | 40% | P/E vs sector median, debt-to-equity, EPS growth (YoY) |
| Relative Strength | 30% | 30-day stock return minus 30-day Nifty return |
| Institutional Flow | 30% | Same shape as swing's smart-money pillar — FII/DII bias + MF verdict |

### How accumulation pillars score

- **Fundamental.** Three sub-components.
  - *Valuation (50% of pillar):* P/E vs sector median. Cheap (< 0.7× sector) = 100. Expensive (> 1.5× sector) = 0.
  - *Debt (25%):* D/E < 1.0 = 100. D/E > 3.0 = 0 AND adds `debt_load` to hard-avoid list — this stock is rejected regardless of other pillars.
  - *Growth (25%):* EPS growth > 20% YoY = 100. Growth < −20% = 0 AND adds `earnings_collapse` to hard-avoid list.
  - Missing inputs (yfinance occasionally lacks a field) degrade each sub-component to 50 (neutral). The pillar refuses to penalise stocks for missing data.

- **Relative Strength.** 30-day return of the stock minus 30-day return of the Nifty.
  - Out-performing by 5% = 100.
  - Matching Nifty = 70.
  - Down 3% relative = 50.
  - Down 7% relative = 25.
  - Worse than −7% relative = 0.
  - This is the empirical "falling less than market" filter. It is the single best predictor that a stock will lead the next rally — but only at the *right* relative-strength threshold.

- **Institutional Flow.** Identical formula to the swing smart-money pillar. Reused intentionally — the inputs and meaning are the same.

### Classification

- **STRONG BUY** — composite ≥ 75. Start a tranche today.
- **BUY** — composite 60–74. Start a tranche this week.
- **WATCH** — composite 45–59. Keep on the radar; will likely qualify after one more dip.
- **AVOID** — composite < 45 OR any hard-avoid reason fired.

Regime does **not** downgrade accumulation classifications. The whole point of accumulation is to be loudest when the market is quietest. A STRONG_BUY in BEAR is the highest-value signal the system produces.

### Tranching

Accumulation positions are always built in tranches. The defaults:

- **Tranche 1** = ⅓ of the budgeted position. Bought when the candidate first qualifies.
- **Tranche 2** = ⅓ more. Triggered when the price drops 8% below the T1 entry.
- **Tranche 3** = final ⅓. Triggered at −15% from T1.

If the stock never drops, the position stops at T1. If the stock drops and then bounces, the average cost is lower than if you'd bought all at once. The downside is being early — the position is at a loss until the bounce. The system does not pretend this is comfortable; it just refuses to all-in on a single timing call.

---

## 8. The market regime detector

Regime is a single classification of the Nifty index, computed each weekend.

- **BULL.** Nifty close above its 50-day EMA AND 50-day EMA slope > 0 over the last 20 sessions.
- **BEAR.** Close below 50-day EMA AND slope < 0.
- **SIDEWAYS.** Anything else — close within ~2% of EMA50 OR slope flat.

The three numbers reported alongside the trend label are:

- *Slope* — the daily change of the 50-day EMA, normalised. A slope of 0.005 means the EMA is rising ~0.5% per session.
- *Distance from EMA50* — how far the index sits above or below its trend mean. A distance of −2.47% means Nifty closed 2.47% below the 50-day EMA.
- *Sector RS map* — for each of 12 sector indices, the 30-day return divided by Nifty's 30-day return. Above 1.0 = outperforming. The map drives the breakout bundle's "sector RS top 3" gate and the regime pillar's sector sub-score.

The regime is persisted weekly. When it flips from BEAR to BULL (or the reverse), the system fires events that re-evaluate accumulation positions for swing-readiness and notify the user.

---

## 9. The risk manager

Risk is enforced at three levels.

### Per-trade risk

For each trade, the engine computes:

- **Risk per share** = entry − stop loss.
- **Max risk per trade** = capital × max_risk_pct (default 5%, configurable).
- **Shares by risk cap** = max risk per trade ÷ risk per share.
- **Shares by capital cap** = (capital × max_pct_capital_per_trade) ÷ entry price.
- **Suggested shares** = min of the two.

The first cap protects against catastrophic loss from any single trade. The second prevents over-concentration regardless of how tight the stop is. Both must hold.

### Portfolio-level risk

- **Max open positions (advisory)** — soft warning when more than 4 swing positions are open. Concentration risk.
- **Max open positions (hard)** — refusal to open more than 10 swing positions. Beyond that, you cannot effectively monitor everything.
- **Capital budget split** — swing pool + accumulation pool + cash reserve must sum to 100%, and cash reserve has a 10% hard floor. Settings UI rejects edits that break this.

### Risk/Reward floor

The R:R pillar in the scoring rubric scores 0 for any setup with R:R below 1.5×. Because BUY requires R:R > 0, this is functionally a hard floor. A 1.4× R:R setup will *never* score BUY no matter how strong the technicals or fundamentals look. This is the single biggest discipline lever — it forces the system to wait for asymmetric setups rather than chase low-reward marginal moves.

### What about position sizing on accumulation?

Different model. Accumulation does not use a per-trade ATR stop. The size is dictated by the tranche schedule and the budget cap. Each new tranche is validated against the total accumulation budget so the system cannot accidentally over-commit.

---

## 10. The agent graph (LLM layer)

Some pieces of the analysis are not arithmetic — they require reading text, interpreting structure, or producing a thesis paragraph. For those, Plutus uses LLM calls in a specific shape called an **agent graph**.

The graph runs once per top-20 candidate during the weekly run. Each "node" is a focused LLM call with a tight scope; outputs from upstream nodes feed downstream nodes.

| Node | Job | Output shape |
|---|---|---|
| `fetch_data` | Pulls OHLCV, indicators, news, FII/DII, MF, regime, sector RS into a single state object. Not an LLM — just data prep. | dict of dataframes + metadata |
| `technical` (LLM) | Reads the indicator dataframe and writes a structured assessment: trend, entry zone, stop, T1, T2, confidence. | JSON |
| `sentiment` (LLM) | Reads the news headlines and writes a polarity verdict + material-event flag + 1-line summary. | JSON |
| `smart_money` (LLM) | Interprets the FII/DII + MF signals and writes a verdict (`bullish_flow`, `neutral`, `bearish_flow`). | JSON |
| `risk_manager` (LLM) | Takes the technical node's entry/stop/target and validates against capital + risk rules. Returns suggested share count + risk budget. | JSON |
| `scoring` | Pure arithmetic — runs the 5-pillar rubric. Not an LLM. | ScoreBreakdown + Classification |
| `narrative` (LLM) | Writes the human-readable thesis paragraph and the top 3 risk flags for the dashboard card. | text |
| `save_recommendation` | Persists the recommendation row. | DB row |

### Why LLMs only for parts of this

LLMs are good at: interpreting news, distilling unstructured text, writing prose. They are bad at: deterministic arithmetic, repeatable scoring, anything that needs to be back-testable. The graph splits responsibilities accordingly. The scoring node is deterministic, the narrative node is generative, and the recommendation is *gated by the deterministic score*, not by the narrative.

This matters because it means the system's behaviour is reproducible. Running the same inputs twice produces the same recommendation. The narrative may phrase the thesis differently, but the BUY/WATCH/HOLD/AVOID decision is identical.

### Cost

The LLM layer uses DeepSeek-V4-Flash via OpenRouter — extremely cheap (cents per weekly run). Token cost is a non-issue at the current scale. Latency adds 5–10 seconds per stock (about 20 minutes for the full top-20 run), which dominates the wall-clock time of the weekly job.

---

## 11. The backtesting harness

Each strategy bundle gets back-tested over a rolling 90-day window every weekly run. The harness:

1. Replays the bundle's entry rule day by day over the last 90 trading days.
2. For each entry, simulates the exit using the bundle's stop/target rules.
3. Records win rate, average winner, average loser, expectancy, Sharpe, and trade count.
4. Stamps the result on the candidate's record.

The best-Sharpe bundle is what the scoring rubric uses for the "backtest validation" sub-component of the Technical pillar.

### Insufficient data guard

Indian data quality is uneven. Some symbols only have a few weeks of usable history (recent IPOs, low-liquidity names). The harness refuses to run if fewer than the minimum required bars are available — it raises `InsufficientDataError` rather than producing a meaningless Sharpe like −93. This guard was added after an early bug where RELIANCE Trend 90d returned Sharpe −93 because yfinance only returned 0–10 bars before EMA50 warm-up.

### Walk-forward validation

For strategies that look promising in 90-day rolling backtests, a second tool — the walk-forward harness — splits the period into train / validate / test slices and reports In-Sample-vs-Out-of-Sample Sharpe. A strategy that backtests well IS but degrades OOS is flagged as overfit. This is the gate that decides whether a bundle is "in" or "experimental" in the Composite weighting.

---

## 12. The outcome tracker

Every recommendation the system makes gets tracked daily after it is made. Mon–Fri at 16:30 IST, a job walks through each open recommendation and asks:

- Did the stock hit T1 within the hold window? → `HIT_T1`
- T2? → `HIT_T2`
- Stop loss? → `STOPPED`
- Did the position run past `hold_days_max` without hitting anything? → `EXPIRED`
- Did the price drop straight through the SL within 3 days of a BUY signal? → `WRONG_DIRECTION` (the headline failure metric)

For every closed trade, the system also records:

- **MFE** — Maximum Favourable Excursion. How high did the stock get before the position closed?
- **MAE** — Maximum Adverse Excursion. How deep did it draw down?

MFE / MAE are the most useful trade-quality metrics that exist. They tell you whether your stops are too tight (high MFE on stopped trades = "you got out before it ran") or your targets are too greedy (high MAE on winners = "you held through too much pain").

Every outcome is tagged with: the **score bucket** at signal time, the **bundle** that triggered it, and the **regime** that day. This enables the calibration loop.

---

## 13. The self-finetuning loop (postmortem)

Once enough closed trades exist (≥ 30 per bucket), a weekly postmortem job runs three nested loops:

### Reporting loop (always on)

Replays the closed-trade ledger from the last 30/60/90 days and produces a calibration report:

- Realised win rate per score bucket (70–80, 60–70, etc.) vs the rubric's expected win rate.
- Realised win rate per bundle. Catches chronic underperformers.
- Realised win rate per regime at signal time. Validates the regime gate.
- Average MFE / MAE per bucket.
- Top 5 best calls and top 5 worst calls — for hand review.
- Count of WRONG_DIRECTION outcomes — the headline failure metric.

Appended to the weekly journal regardless of whether any BUYs were issued.

### Suggestion loop (gated)

When a bucket's realised win rate diverges from the expected by more than 15 percentage points for two consecutive weeks, the system writes a tuning *suggestion* — not an action — to a queue:

> *Score 70–80 bucket: target 60% win rate, realised 38% over n=47. Suggest dropping technical pillar weight from 40 → 35 and lifting regime pillar 15 → 20.*

Suggestions surface in the Settings tab as `[Apply] [Reject] [Defer]`. On Apply, the change is logged with a reference to the report that triggered it, and the next weekly run uses the new weights. Nothing changes without user consent.

### Auto-tuning loop (off by default)

A narrow set of knobs (bundle weights inside the Composite, score thresholds) can be set to auto-retune. Constraints when enabled:

- Never more than one knob per week.
- Compares 12-week trailing win rate before/after; rolls back if rate drops > 5pp over 4 weeks.
- Never touches pillar weights or bundle entry rules automatically.

This is deliberately conservative. The whole loop is designed to *suggest*, log, and survive being wrong rather than to optimise aggressively on small samples.

---

## 14. The alert system

Telegram-first, WhatsApp queued for future. Each alert has a 1-hour cooldown per (position, alert type) so the user is not spammed.

### Swing alerts (intraday, every 15 min during NSE hours)

| Alert | Triggers when | Message |
|---|---|---|
| Pre-SL warning | LTP is within 1% of stop loss | "⚠️ SELL ALERT: TICKER approaching stop loss. LTP=X, SL=Y. Distance 0.8%. Consider exit before close." |
| T1 hit | LTP crosses T1 | "🎯 T1 HIT: TICKER hit first target. Consider partial exit + trail SL to entry." |
| T2 hit | LTP crosses T2 | "🎯🎯 T2 HIT: TICKER hit second target. Consider full exit." |
| Trend invalidated | Daily close below EMA20 for a long held > 5 days | "⚠️ TREND INVALIDATED: TICKER closed below EMA20." |

### Accumulation alerts (intraday + on regime change)

| Alert | Triggers when | Message |
|---|---|---|
| T2 tranche trigger | LTP drops to t1_entry × (1 − t2_drop_pct) | "💰 T2 TRIGGER HIT: TICKER at ₹X — 8% below T1. Consider adding tranche 2." |
| T3 tranche trigger | LTP drops to t1_entry × (1 − t3_drop_pct) | "💰💰 T3 TRIGGER HIT: TICKER at ₹X — 15% below T1. Final tranche." |
| Bull ready | Regime flipped BEAR→BULL AND the accumulation position re-scores as swing BUY | "📈 BULL READY: 3 of your accumulation positions now swing BUY. Review and decide hold vs trim." |

The bull-ready alert is the payoff of the whole dual-mode design. If you've been buying HDFCBANK in tranches at ₹1,640 average during the bear, and Nifty flips BULL with HDFCBANK at ₹1,720, you receive one Telegram message saying "you are now profitably positioned in a BUY-rated stock." From there it's your call whether to keep it as a long-term hold or take the swing trade.

---

## 15. The weekly cadence

| When | Job | Output |
|---|---|---|
| Sunday 18:00 IST | Swing weekly run | `WeeklyRun` row + 20 `Recommendation` rows |
| Sunday 18:25 IST (approx) | Accumulation weekly run | `AccumulationRun` row + ~100 `AccumulationCandidate` rows |
| Sunday 18:30 IST | Postmortem report | Markdown digest appended to `weekly_runs.md` |
| Monday 09:10 IST | Re-validation of last week's recommendations | Updates to recommendation status |
| Mon–Fri 16:30 IST | Outcome tracker | Closed-trade tagging + MFE/MAE update |
| Every 15 min during NSE hours (09:15–15:30 IST) | Position monitor | T1/T2/SL/trend invalidation + tranche-trigger alerts |
| On regime flip | Bull-ready re-scoring | One BULL_READY alert per qualifying accumulation position |

Nothing runs outside these windows — there is no 24/7 polling. The system sleeps during off-hours and weekends.

---

## 16. Where the edge is supposed to come from

Honest accounting of why this system might beat doing nothing:

1. **Discipline beats discretion.** The rubric refuses to BUY anything below R:R 1.5×, refuses to BUY in bear regime, refuses to BUY against a material negative event. Most retail losses come from violating exactly these rules. A system that cannot violate them removes a major leak.

2. **ATR-anchored sizing.** Position sizes are tuned to the stock's typical move, not to a fixed share count. You will hold ten different stocks at ten different position sizes — and that is correct. Most retail traders use a flat ₹ position, which over-concentrates risk in volatile names.

3. **Bundle ensemble.** Seven independent strategies, ranked by recent backtest. The Composite bundle requires multi-lens agreement. This trades trade frequency for higher win rate — fewer signals, better signals.

4. **Regime gating.** Strategies that work in trends don't fire in chop. Strategies that work in chop don't fire in raging bulls. The whole engine produces fewer signals than a single always-on strategy, but each one is in its right environment.

5. **Dual mode.** Bear markets are when most retail capital sits idle or panics. Accumulation mode turns them into the build phase. By the time the regime turns, the patient capital is already in position — that is the asymmetric edge.

6. **Closed feedback loop.** Every recommendation is tracked to outcome. Every outcome is tagged by bucket / bundle / regime. The postmortem surfaces calibration drift before it becomes a real-money problem. You will know within 3–6 months whether the rubric is delivering the win rate it promised.

7. **No leak from LLM.** The LLM does not vote on the recommendation. It only writes the thesis. The decision-making layer is deterministic and back-testable. Most "AI trading" systems lose money because the model lies smoothly. Ours cannot — the recommendation comes from arithmetic, not from a sentence.

---

## 17. What this system explicitly does NOT do

- **Real order execution.** Plutus does not place trades. It surfaces ideas, tracks mock portfolios, and sends alerts. Order entry is your job, manually, through your own broker.
- **Options, F&O, intraday scalping, pair trades.** Equity cash only, swing + accumulation only.
- **Short selling.** Long-only.
- **Recommendation guarantees.** This is a research tool. The score is calibrated against historical outcomes; future outcomes are not promised.
- **Black-box reasoning.** Every BUY/WATCH/HOLD/AVOID can be traced back to specific input values through the rubric. You can interrogate any score.

---

## 18. Reading the dashboard

Three modes appear in the sidebar:

- **Swing.** Signals (this week's screen), Positions (open swing trades, mock-tracked).
- **Accumulation.** Candidates (latest screen ranked by accum score), Tranches (open positions and their tranche state).
- **Shared.** Home (dual-mode overview, regime, capital split), Settings (params, budget split), Strategy lab (backtest comparison).

On every page, the top-left corner shows the current Nifty regime in colour: green for BULL, amber for SIDEWAYS, red for BEAR. The dashboard never lets you forget what regime you are trading in.

When a signal is missing, the dashboard tells you why. "0 BUY signals — Nifty is BEAR; switch to Accumulation mode for current actionable picks" is a far better user experience than an empty table.

---

## 19. The one thing to remember

The rubric, the bundles, the agents, the alerts, the postmortem — all of it serves one purpose: **make the decision boring and the execution disciplined**. The exciting part of trading is the entries; the unprofitable part is everything that surrounds them. Plutus is designed to mechanise the boring 90% so that the 10% requiring judgement gets your full attention.

If the system is doing its job, the trader's workflow looks like:

1. Open the dashboard once a week. Review the new signals.
2. Place the trades you agree with, sized as the system suggests.
3. Wait for Telegram. Act on alerts. Don't intervene between alerts.
4. Read the postmortem at month-end.
5. Tune one knob if the calibration says you should. Otherwise change nothing.

That's the contract. Everything in this document supports that workflow.
