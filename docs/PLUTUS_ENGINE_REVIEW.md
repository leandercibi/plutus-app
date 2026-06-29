# Plutus Engine — Trader's Review

A critical read of `PLUTUS_ENGINE.md` from the seat of someone who actually swing trades NSE cash and accumulates for the long term. The goal here is not to praise the architecture (it's clean) but to stress-test the *metrics* that decide what gets bought — because that's the only part that touches my P&L.

Verdict up front: the skeleton is genuinely good. Deterministic scoring, regime gating, ATR sizing, and a closed outcome loop are the right bones. But several of the metrics are calibrated on assumptions that don't survive contact with how Indian equities actually move. The most dangerous parts are the ones that *look* rigorous (Sharpe-seeded bundle selection, the score buckets) but rest on sample sizes too thin to trust.

---

## 1. The things that are right (so I don't bury them)

- **The LLM doesn't vote.** Correct and non-negotiable. Arithmetic decides, prose explains. This is the single best design decision in the doc.
- **ATR-anchored sizing over flat ₹ positions.** This is what separates people who survive from people who blow up on one volatile midcap. Good.
- **R:R 1.5× hard floor.** The discipline lever. I'd actually argue it's too *low* (more below), but the existence of a non-negotiable floor is right.
- **Regime gating swing vs accumulation.** The dual-mode idea is the real intellectual edge here. Stepping aside in bear instead of forcing trades is what most retail can't do emotionally.
- **MFE/MAE tracking.** Most retail tools never capture this. It's the only honest way to know if stops are too tight or targets too greedy.

Now the critique.

---

## 2. The Technical pillar is 40% — and it's mostly trend-following in a market that whipsaws

The Technical pillar weights 40% of the swing composite, and inside it:
- Trend alignment 30%
- Momentum/RSI 25%
- Volume 15%
- MACD 15%
- Best-bundle Sharpe 15%

**Problem 1 — Trend + Momentum + MACD are all the same bet.** Trend alignment (EMA stack), RSI position, and MACD direction are heavily collinear. When a stock is in a clean uptrend, all three light up together; when it chops, all three go ambiguous together. So the Technical pillar isn't five independent signals — it's roughly *two* (trend/momentum as one cluster, volume as the other) wearing five hats. The pillar is less diversified than the weights imply. In NSE midcaps, which spend a lot of time in violent sideways ranges, this means the Technical score will swing hard on what is essentially one factor.

**Suggestion:** Either collapse trend/RSI/MACD into a single "trend-momentum" sub-score and free up weight for something genuinely orthogonal (breadth, volatility regime of the stock itself, or a mean-reversion flag), or explicitly decorrelate them. Right now 70% of the technical weight is one idea.

**Problem 2 — Volume ratio ≥ 1.3× is doing a lot of heavy lifting and it's easily faked.** A single block deal, an index rebalance, or an F&O expiry day will spike volume 1.3× with zero directional information. Volume confirmation is good in principle but raw volume ratio is noisy on NSE. I'd want delivery-percentage volume (NSE publishes it) rather than total traded volume — delivery volume is far harder to fake and is the actual "conviction" signal. Total volume includes intraday churn that tells me nothing about whether anyone is *holding*.

---

## 3. Best-bundle-by-Sharpe over 90 days is the most overfit number in the system

This is my biggest concern. The doc says seven bundles each backtest over a rolling 90-day window, and **the highest-Sharpe bundle seeds the trade plan**.

- 90 trading days is ~4.5 months. For a swing strategy holding 3–10 days, that's maybe 8–25 trades per bundle *if it fires often* — and several of these bundles (PEAD, VCP, SMC) will fire far less. A Sharpe computed on 5–12 trades is statistical noise. Picking the *max* across seven such noisy estimates is textbook multiple-comparisons bias: you are systematically selecting the bundle that got lucky in the last quarter, not the one with edge.
- This actively *anti-selects*. The bundle that looks best over 90 days is disproportionately the one that's been most in-phase with the recent regime — i.e., the one most likely to mean-revert to mediocre right when you start trusting it.

**Suggestions:**
1. Don't pick the max. Use a shrinkage estimator — pull each bundle's Sharpe toward the cross-bundle mean proportional to its trade count. A bundle with 6 trades should barely move off the prior.
2. Require a minimum trade count (say n ≥ 20) before a bundle is *eligible* to seed the plan; below that it's "supporting context" only.
3. Weight by walk-forward OOS Sharpe (which the doc already computes) rather than in-sample rolling Sharpe. The walk-forward number is the honest one — use it for selection, not just for the "experimental" tag.
4. Consider seeding the plan from the *Composite* bundle by default and only deferring to a single bundle when its OOS edge is large and stable.

This is fixable and it matters more than anything else in the doc.

---

## 4. Score buckets need to prove they're monotonic before anyone trusts a "70 = BUY" line

The classification draws a hard line at composite ≥ 70 for BUY. The postmortem loop checks realised win rate per bucket — good — but the design *ships* with the 70 threshold as if it's known to be meaningful.

The honest position: until you have ≥ 30 closed trades per bucket *across multiple regimes*, you don't know that score 72 wins more than score 64. The doc even admits an earlier bug returned Sharpe −93. The thresholds (70 / 55 / 35) are reasonable priors but they're priors, not findings. The risk is that the dashboard presents a 71 as categorically different from a 69 when the underlying calibration can't yet distinguish them.

**Suggestions:**
- Show a confidence/sample-size badge next to every classification until the bucket has enough closed trades. "BUY (calibration: n=11, low confidence)" is honest; a bare "BUY" is not.
- Treat the 70 line as a *soft* boundary with a dead-zone (e.g., 67–73 is "BUY-watch") until calibration data justifies a hard cut.
- The self-tuning loop's 15pp divergence trigger over *two weeks* is too twitchy on small n — two weeks of swing trades is a handful of outcomes. Gate suggestions on absolute trade count, not just consecutive weeks.

---

## 5. Risk/Reward: a 1.5× floor measured against ATR targets is softer than it sounds

R:R floor of 1.5× sounds disciplined, but look at how it's constructed. Stop is 1.5× ATR, T1 is 2× ATR, T2 is 3× ATR. So the "R:R" being scored is based on the *target you drew*, not the R:R you'll actually realise. Realised R:R depends on hit rate, and the system targets T1 partial exits — meaning effective R:R per trade is closer to the T1 ratio (≈1.33× on the Trend bundle: 2 ATR reward / 1.5 ATR risk) than the headline.

So the "1.5× floor" can pass setups whose *realised* expectancy is barely positive once you account for the fact that most exits happen at T1, slippage, and the stop being hit more often than the target in chop.

**Suggestions:**
- Score R:R on a *probability-weighted* basis using the bundle's own historical hit rate, not on the drawn target distances. expectancy = (P(T1)·R_T1 + P(T2)·R_T2 − P(stop)·R_stop). That's the number that should face the floor.
- Raise the practical floor. For a 3–10 day swing in NSE with real costs (STT, brokerage, slippage on midcaps), I want 2×+ on the drawn target to net a worthwhile edge after the win rate haircut. 1.5× drawn is marginal.

---

## 6. Slippage, costs, and gap risk are absent from the doc

I read all 19 sections and found no mention of transaction costs in the backtest or the R:R math. On NSE cash this is not a rounding error:
- STT, exchange charges, stamp duty, GST, brokerage — round-trip easily 0.1–0.3% on delivery.
- Midcap slippage on a market order can be 0.2–0.5%+ on anything outside the top 100 by liquidity.
- **Gap risk is the swing trader's real killer.** A 1.5× ATR stop is meaningless when the stock gaps 6% against you on overnight news — and the system holds 3–10 days *across* overnight sessions. The backtest simulating exits at the stop price will systematically overstate results because it assumes you exit *at* the stop, not at the gap-down open below it.

**Suggestions:**
- Bake a cost model into the backtest exits and the R:R floor. A strategy that's profitable gross and unprofitable net is worse than useless.
- Model stop fills as the *worse* of (stop price, next-bar open) to capture gap-through. This single change will make the Sharpe numbers honest.
- Add an explicit overnight-gap / event-risk flag (earnings within hold window, F&O ban list, results season) that widens the stop assumption or downgrades the setup.

---

## 7. The PEAD and VCP bundles depend on data that NSE makes hard to get clean

- **PEAD** keys entirely on accurate earnings dates and gap classification. The doc's own caveat ("mis-tagged dates kill it") is the whole ballgame. Indian earnings dates from free feeds are routinely wrong by a day or get revised. If the earnings date is off by one session, the "gap up on earnings" is misattributed and the drift signal is garbage. I'd want this bundle gated behind a *verified* earnings calendar or demoted to experimental permanently until date accuracy is proven.
- **VCP** requires clean contraction detection over multiple pullbacks. On NSE midcaps with circuit filters (5%/10%/20% bands), price action gets artificially truncated — a stock locked in an upper circuit doesn't show a "clean" contraction, it shows a flat line. VCP detection needs to be circuit-aware or it will misread circuit-bound names.

**Suggestion:** Add a circuit-filter awareness layer. Any stock that hit a circuit in the lookback window should be flagged — most pattern logic (VCP, Donchian breakout, swing pivots) is corrupted by circuit behaviour.

---

## 8. Smart Money pillar: FII/DII is market-wide, not per-stock — so what is it actually scoring?

The doc is honest that FII/DII net cash is "market-wide, not per stock." But it's 60% of the Smart Money pillar, applied per candidate. That means every stock on a given day gets the *same* institutional sub-score. It's not a stock-selection signal at all — it's a regime/breadth signal wearing a stock-level costume, and it's partially redundant with the Regime pillar (which also reads market direction).

The per-stock MF accumulation (Tickertape scrape) is the only genuinely stock-specific smart-money input, and it's only 40% of the pillar — and MF holdings data is monthly/lagged, so by the time `ACCUMULATING` shows up, the move may be half done.

**Suggestions:**
- Move FII/DII *out* of the per-stock Smart Money pillar and into the Regime pillar where market-wide flow belongs. That removes double-counting and stops it from pretending to be stock selection.
- Replace the freed weight with something per-stock and timely: delivery-volume trend, bulk/block deal disclosures (NSE publishes daily, genuinely per-stock and timely), or F&O OI build-up for F&O names.
- Treat MF data's lag explicitly — an `ACCUMULATING` verdict from data that's 4 weeks old should decay.

---

## 9. Accumulation rubric: Relative Strength at 30% is the right idea, valuation at 50%-of-fundamental is the trap

The accumulation side is more defensible than the swing side, but two notes:

- **P/E vs sector median, "cheap = 100, expensive = 0"** is a value trap generator. In Indian markets, the cheapest stock in a sector is usually cheap *for a reason* (governance, cyclical peak earnings inflating the E, structural decline). Buying the bottom-decile P/E mechanically is how you accumulate value traps. EPS growth and D/E partly offset this, but valuation is 50% of the fundamental pillar — too much for a single noisy ratio.
- **EPS growth > 20% YoY = 100** rewards base-effect distortions. A company recovering from a bad year shows huge YoY EPS growth that means nothing. YoY single-period growth is the wrong metric — I'd want a multi-year CAGR or at least a smoothed/normalised earnings figure.
- **Relative Strength (30-day stock return − 30-day Nifty return)** is the best metric on the accumulation side and I'd actually weight it *higher*. But 30 days is short for a 3–18 month accumulation thesis. Add a 90-day and 180-day RS and blend — leadership that persists over two quarters is far more predictive than one month.

**Suggestion:** Cap valuation at ≤30% of the fundamental pillar, swap single-year EPS growth for multi-year, and lengthen the RS lookback to match the holding horizon.

---

## 10. Sentiment pillar: 15% weight on a NewsAPI keyword feed is generous for what it can deliver

NewsAPI coverage of Indian small/midcaps is thin and often picks up syndicated wire copy hours-to-days late. The hard-avoid on material negative events is the right *mechanism* (asymmetric: kill the trade, don't reward good news much), and I like that good news caps at 85. But:
- 15% positive weight on a noisy, latency-prone feed means a stale "analyst upgrade" headline can nudge a borderline 68 to a 71 BUY. The upside contribution should be much smaller than the downside veto.
- Keyword-tier sentiment scoring (−5 to +5) is crude; "debt downgrade" in a headline about a *competitor* will misfire unless entity-resolution is solid.

**Suggestion:** Make Sentiment a *veto-mostly* pillar — keep the hard-avoid teeth, but cut its positive contribution to ~5% and reallocate to the Regime or a per-stock flow signal. News should rarely *create* a BUY; it should mainly *prevent* one.

---

## 11. Things I'd want before trading real money on this

A prioritised punch list:

1. **Cost + gap-through model in the backtest.** (Section 6) Highest priority — without it every Sharpe is inflated.
2. **Fix bundle selection.** (Section 3) Shrinkage + min-trade-count + OOS Sharpe instead of max-of-90-day in-sample.
3. **Probability-weighted R:R and a higher net floor.** (Section 5)
4. **Move FII/DII to Regime; add real per-stock flow (delivery %, bulk/block deals).** (Sections 2, 8)
5. **Calibration-confidence badges; soft thresholds until n is sufficient.** (Section 4)
6. **Circuit-filter awareness for all pattern logic.** (Section 7)
7. **Fix accumulation fundamentals: cap valuation weight, multi-year growth, longer RS lookback.** (Section 9)

---

## 12. One structural question the doc doesn't answer

Where is the **correlation / portfolio-construction** check? The risk manager caps per-trade risk and total open positions (4 soft / 10 hard), but nothing in the doc prevents 6 of those 10 swing positions from being the same bet — e.g., six IT midcaps when IT sector RS is hot. Position *count* limits are not *risk* limits when the positions are correlated. In a sector rotation, ten "diversified" trades that are secretly one sector bet draw down together.

**Suggestion:** Add a sector-exposure cap (max N positions or max X% of swing pool per sector) and ideally a pairwise-correlation guard before opening a new position. This is a real and common way these systems blow past their notional risk budget.

---

## Closing

The architecture is honest and the discipline mechanisms are real — this is well above the median "AI stock picker." The weak points are not in the plumbing; they're in metrics that assume cleaner data and larger samples than NSE actually provides. Fix the backtest realism (costs + gaps), fix the bundle-selection overfit, and add per-stock flow and correlation awareness, and this goes from "interesting research toy" to "something I'd size real capital against." As written, I'd paper-trade it for two full quarters across at least one regime flip and watch the WRONG_DIRECTION count and the bucket calibration like a hawk before risking a rupee.


---

# Addendum — Further Design Suggestions

A second pass covering areas the first review didn't reach: universe construction, exit logic, the tuning loop, missing metrics, and operational realism. Same lens — only the things that move P&L or prevent blowups.

## 13. The universe definition is undocumented and it silently decides everything

The doc says Plutus scans "a universe of liquid stocks" but never defines it. This is a bigger deal than it sounds — the universe *is* the strategy. Two issues:

- **Survivorship bias in the backtest.** If the 90-day backtest runs on today's universe, it's implicitly testing only stocks that survived and stayed liquid until today. Delisted, suspended, or crashed-out names are absent, which inflates every win rate. The backtest must run on the *point-in-time* universe as it existed on each historical date.
- **Liquidity drift.** A stock liquid enough to screen on Sunday can be untradeable Monday after bad news halves its volume. The universe filter needs a rolling liquidity floor (e.g., 20-day median *traded value* in ₹, not share count — ₹50L of a ₹3000 stock is very different from ₹50L of a ₹40 stock) and an ADV-relative position cap so the system never sizes a position it can't exit in 1–2 days without moving the price.

**Suggestion:** Document the universe explicitly (index membership? market-cap floor? liquidity threshold?), make the backtest point-in-time, and add a "your position is X% of ADV" warning in the trade plan.

## 14. Exits are mechanical and leave the biggest edge on the table

The whole system is sophisticated about entries and crude about exits — T1 at 2× ATR, T2 at 3× ATR, fixed stop. For swing trading, exit quality drives more of the return distribution than entry quality. Specifics:

- **No trailing logic in the rubric.** The alert system mentions "trail SL to entry" after T1 as advice, but it's a suggestion to the human, not a system rule. A Chandelier exit (highest-high − N×ATR) or an EMA-trail would capture the fat-tailed winners that fixed targets cap. The MFE data the system already collects will show how much is being left behind — I'd bet it's substantial.
- **Targets are symmetric across regimes and bundles share the same ATR multiples.** A breakout in a strong bull should be allowed to run further than a reversal bounce in a sideways tape. Tie target multiples to regime strength, not just to the bundle.
- **Time stop is binary (EXPIRED at hold_days_max).** Better: if a position hasn't reached a meaningful fraction of T1 by the midpoint of the hold window, the expected value of holding is usually negative — scratch it and free the capital. "Dead money" exits beat waiting for the clock.

**Suggestion:** Add a trailing-stop mode and a "scratch if stalled" time-decay rule, both backtestable. Let MFE/MAE data choose the parameters rather than guessing ATR multiples.

## 15. The self-tuning loop can chase noise into the ground

Section 13 of the engine doc is conservative, which is good, but there are still traps:

- **Per-bucket n≥30 is not enough to retune weights.** Win rate on 30 binary outcomes has a 95% CI of roughly ±18pp. The 15pp divergence trigger is *inside the noise band* — you'll fire tuning suggestions on sampling noise routinely. Either raise the threshold, widen the required n, or use a proper sequential test (e.g., SPRT) instead of a fixed-percentage rule.
- **No multiple-testing correction across buckets/bundles/regimes.** You're monitoring many cells simultaneously; some will breach 15pp by chance every week. Without a correction (Bonferroni, or just a higher bar), the suggestion queue becomes a noise generator and the user learns to ignore it — or worse, applies it.
- **Auto-tuning rollback uses 4-week trailing.** Four weeks of swing trades is too few to detect a 5pp degradation with any confidence. The rollback will trigger late, after the damage.

**Suggestion:** Treat all tuning as a statistical inference problem with explicit confidence, not a threshold trip. Display the CI alongside every calibration number so the user sees *uncertainty*, not just a point estimate. Default everyone to "suggest only" and require a manual, dated override to ever enable auto-tune.

## 16. Metrics that are missing entirely

These aren't in the doc and each is a known edge or risk control:

- **Sector/market breadth.** % of universe above its 50-EMA, advance-decline. The regime detector reads only the Nifty index — but the index can be green while breadth rots (a handful of heavyweights masking a weak market). Narrow breadth is the classic late-bull warning. Add breadth as a regime input.
- **Correlation-to-Nifty (beta) at the swing level.** Beta is computed for accumulation but not used to risk-adjust swing sizing. A high-beta name needs a smaller position for the same portfolio risk.
- **Liquidity-at-risk.** Covered in §13 but worth listing as a first-class metric: can I exit this entire position in one session at < X% impact?
- **Earnings-blackout flag for swing.** PEAD aside, a normal swing trade should *know* if earnings fall inside its hold window — that's binary gap risk the entry rule currently ignores.
- **Volatility regime of the stock itself.** ATR percentile vs the stock's own history. Entering when ATR is in the 95th percentile (already-expanded volatility) is very different from entering on a contraction. The VCP bundle captures this implicitly; nothing else does.

## 17. Concentration and capital-allocation logic is too static

The capital split (swing pool / accumulation pool / cash reserve) is a fixed user setting. But the dual-mode thesis is *regime-driven* — so the allocation should breathe with regime, not sit fixed:

- In strong BULL, swing should be allowed a larger share; in BEAR, accumulation. A static split fights the system's own central idea.
- The 10% cash-reserve floor is fine as a floor, but there's no mechanism to *raise* cash when signal quality drops (few high-score candidates = market offering nothing = hold cash). Right now the system will deploy into mediocre setups just because the pool exists. Cash is a position.

**Suggestion:** Make the pool split a function of regime + signal availability, within user-set bounds. "No good signals this week → cash goes up" should be automatic, not a thing the user has to notice.

## 18. The 90-day rolling backtest window is too short to span a regime

A single 90-day window almost never contains both a bull and a bear leg. So a bundle's reported Sharpe reflects whatever regime dominated the last quarter. The regime gate partly handles *when* a bundle fires, but the *performance estimate* used for selection is still regime-contaminated.

**Suggestion:** Report and store bundle stats *conditioned on regime* (Trend-bundle Sharpe-in-BULL vs in-SIDEWAYS), and select using the stat for the *current* regime, not the blended 90-day number. You likely need a longer history (1–2 years) to get enough per-regime trades — which loops back to §13's point about point-in-time universe data.

## 19. Operational and failure-mode gaps

- **Data-source disagreement.** Three OHLCV providers (AngelOne → Jugaad → yfinance) with different adjustment conventions (splits, dividends, bonus). A silent fallback from AngelOne to yfinance mid-history can inject a phantom gap that fires a breakout or trips a stop in the backtest. Add a reconciliation check and prefer a *single* adjusted source per symbol per run; log when a fallback happened so anomalies are explainable.
- **Stale-data trading.** The cache is one trading day. If Sunday's run uses a feed that didn't update for a holiday-shortened week, signals fire on stale candles. Add a freshness assertion (latest candle date == last NSE trading day) before any recommendation is allowed to publish.
- **Alert cooldown vs fast moves.** A 1-hour cooldown per (position, alert type) is sensible against spam, but a stock can blow through the pre-SL warning *and* the stop within that hour on a fast day. The pre-SL and SL-hit alerts shouldn't share a cooldown; an actual stop breach should always fire immediately.
- **Mock vs real divergence.** Mock fills presumably assume execution at the signal/stop price. When the user trades real, their fills will differ, and the outcome tracker (which drives calibration) is recording *mock* outcomes. The calibration loop is therefore tuning against idealized fills, not what the user actually gets. At minimum, let the user log real fills so calibration can run on reality.

## 20. Dashboard / decision-support suggestions

- **Show the score decomposition, not just the number.** A 71 BUY built on a strong Technical + weak everything is a different trade than a 71 built on balanced pillars. Surface the pillar bars on the card so the human can see *why* and apply the judgment the system explicitly reserves for them.
- **Show what would change the verdict.** "This is WATCH; it becomes BUY if R:R reaches 1.6× (needs entry < ₹X) or regime flips BULL." Actionable thresholds beat static labels.
- **Track the system against a benchmark.** The "where's the edge" section claims edge over doing nothing — prove it. The postmortem should report system equity curve vs buy-and-hold Nifty and vs an always-in-Nifty-on-BULL baseline. If the engine doesn't beat "hold Nifty50 index when BULL, cash when BEAR," the complexity isn't earning its keep.

## 21. Prioritised additions to the earlier punch list

In rough ROI order, layered on top of the first review's list:

1. **Point-in-time universe + per-regime bundle stats** (§13, §18) — without this the backtest is fiction; pairs with the §3 overfit fix.
2. **Benchmark the whole system vs Nifty / a trivial regime baseline** (§20) — answers the only question that matters: is this better than an index fund?
3. **Trailing exits + scratch-if-stalled** (§14) — likely the largest single P&L improvement available.
4. **Statistical rigor in the tuning loop (CIs, multiple-testing)** (§15) — stops the system from tuning into noise.
5. **Regime-adaptive capital allocation + cash-as-a-position** (§17).
6. **Breadth + earnings-blackout + liquidity-at-risk metrics** (§16).
7. **Data reconciliation, freshness assertion, decoupled SL alert cooldown** (§19).

## 22. The meta-point

Plutus is over-invested in *entry signal generation* (seven bundles, an agent graph, a five-pillar rubric) and under-invested in the three things that empirically determine whether a swing system makes money: **realistic cost/slippage/gap modeling, exit management, and honest statistical validation against a benchmark.** I'd happily trade a system with three good bundles and excellent exits + cost realism over one with seven bundles and idealized fills. The next phase of work should shift effort from "more ways to find entries" to "prove the entries we have survive real execution and beat the index." That's where the unglamorous, durable edge actually lives.
