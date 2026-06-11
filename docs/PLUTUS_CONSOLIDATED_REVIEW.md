# Plutus — Consolidated Review & Action Plan

This document does three things:

1. **Cross-examines the second trader's review (R2) against mine (R1)** — where we agree, where we conflict, where each of us caught something the other missed, and where R2 is wrong or only half-right.
2. **Resolves the conflicts** with explicit reasoning, so the action plan has one position per issue, not two.
3. **Produces the master action plan** — organized as CHANGE / ADD / REMOVE / IMPROVISE / OPTIMIZE, with priorities and dependencies.

Verdict on R2 first: it's a strong review by someone who clearly trades NSE. Roughly 70% of it independently converges with R1 — which is itself signal: when two independent reviewers hit the same four structural problems, those problems are real, not taste. R2's best contributions are the India-specific operational catches (circuit filters, delivery volume, earnings blackouts, mock-vs-real fills) and the exit-management push. Its weakest moments are two suggestions that contradict facts R1 established (seeding from the Composite bundle while its geometry is broken; stacking a raised drawn-ratio floor on top of an expectancy floor) and one suggestion that quietly contradicts the engine's own core design principle (regime-adaptive pool sharing vs "pools never share budget"). All resolved below.

---

## PART 1 — Where the two reviews agree (independently)

Convergence on a flaw by two independent reviewers is the strongest evidence in this whole exercise. These are no longer opinions; treat them as defects.

| # | Issue | R1 | R2 | Status |
|---|---|---|---|---|
| 1 | **No cost / slippage / gap modeling.** Every backtest number is inflated; gap-through-stop makes realized losses worse than planned 1.5×ATR. | §2.1, §3.5 | §6 | **Confirmed defect — P0.** R2 adds the concrete fill rule: model stop fills as *worse of (stop price, next-bar open)*. Adopt verbatim. |
| 2 | **Best-of-7-bundles by 90-day Sharpe is overfit by construction.** Max of seven noisy estimators on tiny n; selects luck; anti-selects toward regime mean-reversion. | §2.2 | §3 | **Confirmed defect — P0.** R1 adds the *circularity* angle (lucky Sharpe also feeds the Technical pillar — double-dip); R2 adds *use the walk-forward OOS Sharpe you already compute for selection*. Both go in. |
| 3 | **No benchmark.** System cannot distinguish alpha from beta. | §2.3 | §20, §22 | **Confirmed defect — P0.** R2's baseline ("hold Nifty when BULL, cash when BEAR") is sharper than R1's plain buy-and-hold because it tests the regime detector and the stock-picking *separately*. Use all three baselines (see plan). |
| 4 | **R:R pillar scores drawn geometry, not realized expectancy.** Both independently computed the same damning number: Trend bundle effective R:R to T1 ≈ **1.33×, below the system's own 1.5× floor**. | §2.4, §3.6 | §5 | **Confirmed defect — P0.** Replace ratio-of-drawn-distances with probability-weighted net expectancy (see Part 2, Conflict B for the floor question). |
| 5 | **Smart Money pillar: FII/DII is market-wide → zero cross-sectional information, double-counts Regime; MF data is lagged disclosure.** | §3.6, §3.3 | §8 | **Confirmed defect — P1.** R2's fix is cleaner than R1's: *move* FII/DII into the Regime pillar rather than just down-weighting it. Adopt R2's version. Both reviews independently propose the same replacement: **delivery-volume trends + bulk/block deals** (NSE publishes daily, genuinely per-stock). |
| 6 | **Tuning loop fires inside the noise band.** Both computed the same statistic: 95% CI on win rate at n=30 ≈ ±18pp > the 15pp trigger. Both flag multiple-testing across buckets×bundles×regimes. | §3.13 | §15 | **Confirmed defect — P1.** R2 adds SPRT (sequential testing) as the mechanism and "display CIs next to every calibration number" — adopt both. R1 adds: optimize toward **expectancy, not win rate** — R2 missed this and it matters, because a win-rate-optimizing loop will drift the system toward low-R, high-hit-rate trades. |
| 7 | **Point-in-time universe / survivorship bias in backtests.** | §3.11 | §13, §18 | **Confirmed defect — P1.** R2 goes further: the universe is *undocumented entirely*, and the liquidity floor should be **median traded value in ₹**, not share count. Adopt. |
| 8 | **Correlation-blind portfolio risk.** Position-count limits are not risk limits; 10 longs can be one sector bet. | §3.9 | §12 | **Confirmed defect — P1.** R1 frames it as portfolio-heat with correlation haircut; R2 as sector-exposure caps + pairwise-correlation guard. These are complementary layers — implement both (sector cap is trivial; correlation guard is the refinement). |
| 9 | **Breadth missing from the regime detector.** Index-only regime is late and can be green while breadth rots. | §3.8 | §16 | **Confirmed gap — P2.** Same fix: % of universe above 200/50-DMA + advance-decline as regime inputs. |
| 10 | **Accumulation valuation logic is a value-trap generator.** Cheap-P/E-scores-100 mechanically buys the cheapest-for-a-reason names; cyclicals invert the signal at earnings peaks. | §3.7 | §9 | **Confirmed defect — P2.** R2 adds the **base-effect problem in YoY EPS growth** (recovery year shows fake +100% growth) and the concrete fix — multi-year CAGR / normalized earnings, valuation capped ≤30% of the pillar. Adopt R2's specifics. |
| 11 | **Data-source mixing across adjustment conventions = phantom gaps.** | §3.3 | §19 | **Confirmed defect — P1.** Same fix independently: one adjusted source per symbol per run, reconcile on overlap, log fallbacks. |
| 12 | **Sentiment: noisy feed, entity mis-resolution, too much power for what NewsAPI delivers on Indian midcaps.** | §3.6 | §10 | **Confirmed — P1**, but the two fixes differ in degree. Resolved in Part 2, Conflict C. |
| 13 | **Stalled-trade exits missing.** R1: time/no-progress exit in the early window (trend-invalidation alert only arms after day 5). R2: scratch-if-stalled at the hold-window midpoint. | §3.14 | §14 | **Confirmed gap — P1.** Same idea at different points in the trade's life; unify into one no-progress rule (see plan). |

Thirteen independent collisions. The skeleton of the action plan writes itself from this table alone.

---

## PART 2 — Where the reviews conflict, and the resolution

Four genuine conflicts. Each resolved with a position, not a compromise-for-its-own-sake.

### Conflict A — "Seed the trade plan from the Composite bundle by default" (R2 §3.4)

R2 suggests defaulting plan-seeding to the Composite bundle and deferring to single bundles only on large, stable OOS edge. Reasonable instinct — ensembles are more stable than maxima.

**But R1 established that the Composite's geometry is currently broken**: it takes the *tightest* of the three sub-bundle stops and the *nearest* of the three targets — the minimum-R:R combination, maximally exposed to noise stop-outs with the smallest payoff. Seeding everything from the Composite *as currently designed* would make the system's default plan the worst-geometry plan. R2 evidently didn't notice this clause in §5 of the engine doc.

**Resolution — sequence matters:**
1. First, fix Composite geometry. High multi-lens agreement should buy *room and reward*, not tightness: stop = **widest** structural stop among agreeing sub-bundles (or median), target = probability-weighted blend, not the nearest.
2. *Then* adopt R2's default-to-Composite seeding, with R2's own escape hatch (defer to a single bundle only when its pooled, per-regime, OOS, shrunk Sharpe is decisively better).
3. R2's suggestion is good **conditional on the fix**; adopted as a P1 that depends on the P0 geometry repair.

### Conflict B — "Raise the drawn-target R:R floor to 2×" (R2 §5)

R2 wants the floor on drawn targets raised from 1.5× to 2×+. R1 wants the floor moved off drawn geometry entirely, onto **net probability-weighted expectancy**.

These overlap but are not the same, and stacking both naively is wrong: once the floor is expectancy-based (which both reviews endorse as the correct number — R2 even writes the formula), a *separate* raised drawn-ratio floor becomes redundant at best and double-penalizing at worst. A 1.6× drawn setup with a 60% historical T1 hit rate can have better net expectancy than a 2.2× drawn setup hit 25% of the time; a hard 2× drawn floor would kill the better trade and keep the worse one — exactly the error the expectancy floor exists to fix.

**Resolution:**
- **Primary gate: minimum net expectancy** per trade — `E = P(T1)·R_T1 + P(T2)·R_T2 − P(SL)·R_SL`, computed with **pooled per-regime hit rates** and **after** the cost model. Floor it at a meaningful positive value (e.g., ≥ +0.3R net; calibrate once cost model exists).
- **Secondary gate: keep a modest drawn-ratio sanity floor (1.5× on the *probability-realistic* target)** purely as a guard for new bundles/stocks with insufficient hit-rate history, where the expectancy estimate is itself untrustworthy. R2's instinct ("1.5× drawn is marginal after costs") is then absorbed by the cost-adjusted expectancy gate rather than by an arbitrary 2× line.
- Verdict: **R2 directionally right, mechanically wrong; R1's mechanism wins, R2's severity calibrates it.**

### Conflict C — Sentiment: "corroborated hard-kill" (R1) vs "veto-mostly at ~5% weight" (R2 §10)

Not fully contradictory, but they pull on different ends. R1's concern: the hard-kill is *too trigger-happy* (one keyword mis-tag — e.g., a competitor's debt downgrade — nukes a good setup), so the veto needs corroboration. R2's concern: the *positive* contribution is too large (a stale upgrade headline can push a 68 to a 71 BUY), so cut weight to ~5% and keep the veto teeth.

R2 keeps full-strength teeth on the exact noisy feed R1 showed will mis-fire. R1 keeps 15% positive weight on a feed R2 correctly shows can't earn it.

**Resolution — both, they compose cleanly:**
- **Cut the pillar's positive weight to ~5%** (R2), reallocating 10% — sending it to the new per-stock flow signal (delivery/bulk-block) rather than Regime, since Regime is already gaining FII/DII from Conflict-free item #5.
- **Make the hard-kill require corroboration** (R1): two independent headlines naming the entity, *or* one headline plus a price/volume confirmation (gap down on volume), *or* a structurally verifiable event class (exchange filing, rating-agency action). Single uncorroborated keyword match → graded penalty, not kill.
- Plus R1's separately-discovered inconsistency that R2 missed entirely: **the engine doc describes sentiment twice — as a deterministic keyword-tier scorer (§3/§6) and as an LLM node (§10)**. Two sources of truth for a classification-flipping input. The deterministic path must be the one that gates; the LLM may add color only.

### Conflict D — "Regime-adaptive capital allocation" (R2 §17) vs the engine's own "pools never share budget" principle

R2 wants the swing/accumulation split to breathe with regime (more swing in BULL, more accumulation in BEAR) and cash to rise automatically when signal quality drops. The instinct is right — a static split does fight the dual-mode thesis. But R2's version quietly contradicts a deliberate design principle of the engine ("They never share budget"), and it collides with the capital-handoff problem R1 raised in §3.1: when the regime flips BULL, accumulation capital is *deployed in open tranches* — it isn't free to migrate. An auto-rebalancer that tries to move committed capital will either force-sell accumulation positions (destroying the patient-capital thesis) or be a no-op exactly when it matters.

**Resolution — adopt the idea, constrain the mechanism:**
- Dynamic allocation applies to **uncommitted capital only**. Deployed tranches and open swing positions are never force-migrated by regime.
- Regime tilts the split of *new* deployable capital within user-set bounds (e.g., swing share ranges 30–70%, set by regime), and the bull-ready flow remains the designed mechanism by which accumulation capital *voluntarily* converts.
- **Cash-as-a-position is adopted in full** — it's R2's best allocation idea and conflicts with nothing: when the week's screen produces few high-score candidates, undeployed capital stays in cash *by rule*, with the dashboard saying so ("market offered 1 qualifying setup; 62% of swing pool held in cash"). This kills the deploy-into-mediocrity failure mode.

---

## PART 3 — What each review caught that the other missed

### R2's unique catches (validated — these go in the plan)

1. **Technical pillar collinearity (§2).** Trend alignment + RSI + MACD are one factor wearing three hats; ~70% of the Technical pillar is a single trend-momentum bet that whipsaws as one unit in NSE's violent sideways ranges. R1 missed this and it's correct — the pillar's diversification is cosmetic. *Fix: collapse into one trend-momentum sub-score; free the weight for orthogonal inputs (stock's own ATR percentile, a mean-reversion flag).*
2. **Delivery-percentage volume over raw volume ratio (§2).** Raw 1.3× volume is trivially polluted by block deals, expiry days, rebalances. NSE publishes delivery %; delivery volume is the conviction signal. (R1 mentioned delivery % only as a smart-money candidate; R2 correctly applies it to the volume-confirmation gate itself.)
3. **Circuit-filter awareness (§7).** India-specific and excellent: stocks locked in 5/10/20% circuit bands produce truncated price action that corrupts VCP detection, Donchian breakouts, and swing pivots. A flat line at the band is not a contraction. *Any stock that hit a circuit in the lookback gets flagged and pattern logic suppressed.* R1 missed this entirely.
4. **Earnings-blackout flag for ordinary swing trades (§16).** PEAD aside, a normal 3–10 day swing should know whether results fall inside its hold window — that's binary gap risk the entry ignores. Cheap to add, obviously right.
5. **Mock-vs-real fill divergence poisons calibration (§19).** The outcome tracker — the input to the entire tuning loop — records *mock* fills at signal/stop prices. The calibration loop is tuning against fills nobody gets. *Let the user log real fills; calibrate on reality where available.* Arguably the sharpest single observation in R2.
6. **Freshness assertion (§19).** Latest candle date must equal the last NSE trading day before any recommendation publishes; holiday-shortened weeks otherwise produce signals on stale candles.
7. **Decoupled SL-alert cooldown (§19).** Pre-SL warning and actual SL breach must not share a 1-hour cooldown; a breach always fires immediately. Obvious once stated; dangerous until fixed.
8. **Trailing exits + MFE-driven parameterization (§14).** Chandelier (highest-high − N×ATR) or EMA-trail after T1, with the already-collected MFE data choosing parameters instead of guessing multiples. R1 flagged exits only via the early-window no-progress gap; R2's broader claim — *the system is over-invested in entries and under-invested in exits, and exit quality drives more of the return distribution* — is correct and becomes a theme of the plan.
9. **Per-regime bundle statistics (§18).** A 90-day blended Sharpe is regime-contaminated even after fixing pooling; store and select on Sharpe-in-current-regime. Needs 1–2 years of history — which couples to the point-in-time universe work.
10. **Calibration-confidence badges + soft threshold dead-zone (§4).** Until a bucket has enough closed trades across regimes, show "BUY (calibration n=11, low confidence)" and treat 67–73 as a BUY-watch band rather than pretending 71 ≠ 69. Honest UI; adopt.
11. **Score decomposition + counterfactual on the card (§20).** Show pillar bars (a 71 from lopsided Technical ≠ a balanced 71) and "becomes BUY if R:R reaches 1.6× (entry < ₹X) or regime flips." Directly serves the engine's own stated philosophy of reserving judgment for the human.
12. **RS lookback blending for accumulation (§9).** 30-day RS is too short for a 3–18 month thesis; blend 90/180-day. Persistence over two quarters is the predictive version.

### R1's unique catches (R2 missed — these stay in the plan)

1. **The 2% vs 5% risk contradiction.** Engine §4 says 2% per trade; engine §9 defaults `max_risk_pct` to 5%. At 5% × 10 positions, a correlated gap-down risks ~half the pool. R2 attacked correlation but never noticed the engine contradicts itself on the base number.
2. **Composite bundle geometry bug** (tightest stop + nearest target = lowest R:R labeled "high conviction") — the basis of Conflict A.
3. **The "no LLM leak" claim is overstated.** The sentiment LLM's material-event flag can force AVOID; the smart-money LLM writes a pillar input; the technical LLM writes the entry/stop/targets the R:R pillar consumes. LLM-extracted features absolutely enter — and can flip — the "deterministic" decision. Fix: anything classification-flipping must come from the deterministic path.
4. **The dual sentiment-path inconsistency** (keyword scorer vs LLM node — which feeds the score?).
5. **Drawdown governor.** Nothing throttles risk after a losing streak; add a circuit breaker (halve per-trade risk below −X% from pool high-water mark, restore on recovery).
6. **Accumulation has no exit at all** — no thesis-invalidation (D/E spike, earnings collapse *after* entry), hard-avoid checks fire only at initial scoring, never at tranches. R2's exit section (§14) covers swing only; the accumulation side's "hold through anything, exit only via bull-ready" is the bigger hole.
7. **Tranche triggers are volatility-blind** (−8/−15% fixed means different things on FMCG vs high-beta smallcap → ATR-normalize) **and tranches don't re-validate the thesis** before averaging down.
8. **Regime detector adds India VIX** as the volatility dimension (R2's per-stock ATR percentile is related but is a stock-level metric; market-level VIX is a separate input).
9. **Weekend-gap exposure + Monday re-validation must re-run entry gates** against Monday's open, not just update status.
10. **Weekly cadence structurally lates the time-sensitive bundles** (Breakout, PEAD go stale between Sundays) — either a midweek mini-screen for those two or weight them down for staleness.
11. **The capital-handoff question at regime flips** (what happens to mid-flight tranches when swing suddenly wants capital) — which became the constraint that fixed R2's Conflict-D proposal.
12. **Liquidity-at-size cap** as ≤10–15% of 20-day ADV — R2 names the metric class (§13, §16 "liquidity-at-risk") and the ₹-traded-value floor; R1 supplies the position-sizing cap number. Merged in the plan.

### Where R2 is right but should be tempered

- **"Demote PEAD permanently until date accuracy is proven" (§7).** Agree with the gate, resist the "permanently." PEAD post-costs on NSE may genuinely be net-negative (R1's position), so the honest sequence is: gate behind a verified earnings calendar → run it paper-only through one earnings season with the cost model on → keep or kill on evidence. Same evidence-first treatment R1 proposed for SMC (which R2 didn't examine at all — SMC's pseudo-quant slot in the ensemble remains an R1-only concern and stays in the plan).
- **"Weight accumulation RS higher" (§9).** Directionally fine, but only *after* lengthening the lookback — up-weighting a 30-day RS would amplify exactly the short-horizon noise R2 complains about two sentences earlier. Sequence: blend 90/180-day first, then consider 30% → 35–40%.

---

## PART 4 — Master Action Plan

Every item carries its source (R1 / R2 / Both) and priority. **P0 = changes what the numbers mean; do before trusting any backtest. P1 = contradictions and risk holes. P2 = measurement honesty. P3 = edge refinement.** Dependencies are marked, because several R2 suggestions are only safe after an R1 fix (and vice versa).

### A. CHANGE (existing behavior that is wrong as designed)

| # | Item | Source | Pri |
|---|---|---|---|
| A1 | **Backtest fills:** stop fills = worse of (stop price, next-bar open); entries at next-bar open + slippage; confirm no same-bar look-ahead. | Both | **P0** |
| A2 | **Bundle selection:** pool backtests across the universe (not per-stock); min pooled trade count (n ≥ 20–30) for plan-seeding eligibility; rank by **walk-forward OOS, per-regime, shrunk** Sharpe (shrinkage toward cross-bundle mean ∝ trade count); never raw max of 90-day in-sample. | Both | **P0** |
| A3 | **Break the circularity:** the per-stock lucky Sharpe stops feeding the Technical pillar; the backtest sub-score uses the pooled per-regime bundle stat. | R1 | **P0** |
| A4 | **R:R pillar → net probability-weighted expectancy** (pooled per-regime hit rates, after costs); floor on expectancy ≥ +0.3R net (calibrate); retain 1.5× drawn-target ratio only as a fallback sanity gate where hit-rate history is insufficient. Resolves the Trend-T1-below-floor bug by construction. | Both (mechanism R1, severity R2) | **P0** |
| A5 | **Composite bundle geometry:** widest/median structural stop among agreeing sub-bundles; probability-weighted target — never tightest-stop + nearest-target. | R1 | **P0** |
| A6 | **Resolve 2% vs 5% per-trade risk** — pick one (recommend 1–2% given correlation reality) and make doc + code agree. | R1 | **P1** |
| A7 | **Smart Money pillar restructure:** FII/DII moves into the Regime pillar; per-stock slot filled by delivery-volume trend + bulk/block deals; MF `ACCUMULATING` verdict decays with data age. | Both (mechanism R2) | **P1** |
| A8 | **Sentiment pillar:** positive weight cut to ~5% (freed weight → per-stock flow); hard-kill requires corroboration (2 entity-resolved headlines, or headline + price/volume confirmation, or verifiable filing/rating event); single uncorroborated keyword = graded penalty. One deterministic scoring path — the LLM node may not produce any value that gates classification. | Both + R1 (dual-path fix) | **P1** |
| A9 | **Volume confirmation gate:** delivery-adjusted volume replaces raw volume ratio where delivery % is available; flag expiry/rebalance days. | R2 | **P1** |
| A10 | **Technical pillar de-correlation:** collapse trend-alignment + RSI + MACD into one trend-momentum sub-score; reallocate freed weight to orthogonal inputs (stock ATR percentile, mean-reversion flag). | R2 | **P1** |
| A11 | **Plan seeding default → fixed Composite**, defer to a single bundle only on decisively better pooled OOS per-regime stats. *Depends on A5.* | R2 (conditional on R1's A5) | **P1** |
| A12 | **Accumulation fundamentals:** valuation capped ≤30% of pillar; YoY EPS growth → multi-year CAGR / normalized earnings; RS lookback blended 30/90/180-day (then optionally up-weight RS). | R2 | **P2** |
| A13 | **Tranche triggers ATR-normalized** (not fixed −8/−15%); **each tranche re-validates the fundamental thesis** before averaging down. | R1 | **P2** |
| A14 | **Tuning loop statistics:** sequential test (SPRT) or substantially raised bar + multiple-testing correction across buckets×bundles×regimes; CIs displayed beside every calibration number; calibration conditioned on regime; objective = **expectancy, not win rate**; auto-tune stays opt-in with dated manual override. | Both (+ R1 expectancy objective) | **P1** |
| A15 | **Monday 09:10 re-validation re-runs entry gates** against Monday's open (weekend-gap defense), not status-only. | R1 | **P2** |
| A16 | **Alert cooldowns decoupled:** SL breach always fires immediately, never suppressed by the pre-SL warning's cooldown. | R2 | **P1** (trivial, dangerous until done) |
| A17 | **Universe documented and point-in-time:** explicit membership rule; liquidity floor = 20-day **median traded value in ₹**; backtests run on the universe as of each historical date. | Both (specifics R2) | **P1** |

### B. ADD (missing capabilities)

| # | Item | Source | Pri |
|---|---|---|---|
| B1 | **Cost model** (STT, brokerage, exchange charges, GST, stamp duty) + **slippage model** scaling with position÷ADV and ATR — in backtest *and* live R:R/expectancy. Everything in A1–A4 consumes this. | Both | **P0** |
| B2 | **Benchmarks in every postmortem:** (i) Nifty buy-and-hold; (ii) "Nifty when BULL, cash when BEAR" (isolates regime-detector value); (iii) random-liquid-stock baseline with matched trade count/hold windows (isolates selection skill). | Both (iii R1, ii R2) | **P0** |
| B3 | **Correlation-aware portfolio heat:** sector-exposure cap (max positions / max % of pool per sector) + pairwise-correlation guard before opening; portfolio heat = Σ position risk with correlation haircut. | Both | **P1** |
| B4 | **Drawdown governor:** per-trade risk halves below −X% from swing-pool high-water mark; restores on recovery. | R1 | **P1** |
| B5 | **Liquidity-at-size cap:** position ≤ 10–15% of 20-day ADV; trade plan shows "this position = X% of ADV." | Both | **P1** |
| B6 | **Earnings-blackout flag:** any swing entry whose hold window contains a results date is downgraded or stop-widened; F&O ban-list flag alongside. | R2 | **P1** |
| B7 | **Circuit-filter awareness:** stocks hitting any circuit band in the lookback are flagged; VCP/Donchian/pivot logic suppressed or discounted on them. | R2 | **P1** |
| B8 | **Exit management layer:** (i) trailing mode post-T1 (Chandelier / EMA-trail), parameters chosen from collected MFE data, backtested like any bundle rule; (ii) unified no-progress scratch — if the position hasn't achieved a set fraction of T1 by a set fraction of the hold window, exit (subsumes R1's early-window gap and R2's midpoint rule, and replaces the binary EXPIRED). | R2 (+R1) | **P1** |
| B9 | **Accumulation thesis-invalidation exit:** hard-avoid conditions (D/E breach, earnings collapse) re-checked on every re-score; firing post-entry triggers an exit alert even at a loss. | R1 | **P2** |
| B10 | **Mock-vs-real fill logging:** user can record actual fills; calibration prefers real fills where present and reports mock-vs-real slippage drift. | R2 | **P2** |
| B11 | **Data freshness assertion:** latest candle == last NSE trading day, else the run aborts publication. | R2 | **P2** |
| B12 | **Data reconciliation:** one adjusted source per symbol per run; overlap checks across providers; every fallback logged; corporate-action (split/bonus/dividend) handling explicit. | Both | **P1** |
| B13 | **Regime detector inputs:** breadth (% of universe above 200/50-DMA, advance-decline) + India VIX; breadth-confirmed flips. | Both (VIX R1) | **P2** |
| B14 | **Per-regime bundle stat store** (Sharpe-in-BULL vs in-SIDEWAYS etc.), selection uses the current-regime stat; requires 1–2 yr point-in-time history (couples to A17). | R2 | **P2** |
| B15 | **Cash-as-a-position rule:** few qualifying setups → undeployed capital stays in cash by rule; dashboard states it. | R2 | **P2** |
| B16 | **Bounded regime-adaptive allocation:** regime tilts the split of *uncommitted* capital within user bounds; deployed tranches/positions never force-migrated; bull-ready remains the voluntary conversion path. | R2, constrained by R1's handoff problem | **P3** |
| B17 | **Dashboard:** pillar-decomposition bars on every card; counterfactual line ("becomes BUY if…"); calibration-confidence badges; soft dead-zone (67–73 = BUY-watch) until buckets are calibrated. | R2 | **P2** |
| B18 | **Midweek mini-screen** for time-sensitive bundles (Breakout, PEAD) or an explicit staleness down-weight in the Sunday run. | R1 | **P3** |

### C. REMOVE (or gate pending evidence)

| # | Item | Source | Pri |
|---|---|---|---|
| C1 | **Raw FII/DII from the per-stock Smart Money pillar** — relocated, not deleted (→ A7). | Both | P1 |
| C2 | **PEAD bundle from live seeding** until: verified earnings calendar + one full earnings season paper-traded with the cost model. Keep-or-kill on that evidence. (R2's "permanently" softened to evidence-gated.) | Both | P2 |
| C3 | **SMC bundle's ensemble slot** — re-justify with pooled OOS evidence post-A2 or drop to display-only context. R2 never examined it; R1's pseudo-quant concern stands. | R1 | P3 |
| C4 | **Raw-volume-only confirmation** (superseded by A9). | R2 | P1 |
| C5 | **Win rate as the headline metric** anywhere (dashboard, postmortem, tuning objective) — replaced by expectancy/profit factor with CIs. | R1 | P1 |
| C6 | **The literal "no leak from LLM" claim** in the doc — restate honestly as "no LLM output can gate or flip a classification" *after* A8 makes it true. | R1 | P2 |

### D. IMPROVISE (design-level reframing, not parameter tweaks)

1. **Shift the center of gravity from entries to exits and validation** (R2 §22's meta-point, endorsed): seven entry bundles + an agent graph vs zero cost model, fixed exits, and no benchmark is an inverted effort allocation. The P0 block plus B8 *is* that shift. A system with four honest bundles, trailing exits, and net-expectancy gating beats one with seven bundles and idealized fills.
2. **Reframe the edge claim honestly** (R1 §3.16): the durable edge here is behavioral — discipline, sizing, regime-avoidance — not predictive stock-picking, until B2's benchmarks prove otherwise. The doc should say which edge is which; B2 is what lets it.
3. **Treat every calibration/tuning number as an inference with uncertainty, not a reading on a dial** (R2 §15 framing + R1's noise-band math): CIs everywhere, sequential tests, regime conditioning. The tuning loop's job is to *resist* acting, and to make uncertainty visible when it does.
4. **The human-judgment contract:** the engine doc reserves the final 10% for the trader; B17 (decomposition, counterfactuals, confidence badges) is what actually equips that judgment. A bare "BUY 71" does not.

### E. OPTIMIZE (after the above is live and honest)

1. Per-regime target multiples (bull breakouts run further than sideways bounces) — R2 §14, only meaningful after the cost model and B14 exist.
2. Beta-adjusted swing sizing (beta already computed for accumulation; reuse it) — R2 §16.
3. MFE/MAE-driven stop/target re-derivation per bundle — the data loop both reviews praised, pointed at the parameters both reviews doubt.
4. F&O OI build-up as an additional per-stock flow input for F&O-listed names — R2 §8, after A7's simpler signals prove in.
5. RS weight increase on the accumulation rubric (30% → 35–40%) — only after A12's lookback blend.

---

## PART 5 — Sequencing and the go-live bar

**Phase 1 (P0):** B1 cost/slippage model → A1 fill realism → A2/A3 bundle-selection fix → A4 expectancy gating → A5 Composite geometry → B2 benchmarks. *Until Phase 1 completes, no backtest number in the system means anything — both reviews independently reached this conclusion.*

**Phase 2 (P1):** risk-layer repairs (A6, B3, B4, B5), signal repairs (A7–A11, B6, B7), data integrity (A17, B12), exit layer (B8), tuning statistics (A14), alert fix (A16).

**Phase 3 (P2/P3):** accumulation repairs, regime upgrades, dashboard honesty, allocation breathing, evidence-gated bundle pruning, optimizations.

**Go-live bar (both reviews converge on this):** paper-trade a minimum of **two full quarters spanning at least one regime flip**, with the cost model on and real fills logged, watching WRONG_DIRECTION counts and bucket calibration with CIs — and the system must beat *both* the regime-baseline and the random-selection baseline net of costs before a rupee of real size goes on. If it only beats buy-and-hold but not the regime baseline, the stock-picking layer isn't earning its complexity and the honest product is a regime-switched index strategy with an accumulation sleeve.

---

## Closing

Two independent experienced reviewers hit the same four structural defects — costs, bundle-selection overfit, missing benchmark, and geometry-vs-expectancy in R:R — which upgrades them from opinion to fact. R2's distinctive value is operational India-market realism (circuits, delivery volume, earnings blackouts, mock-fill contamination) and the exits-over-entries reframing; R1's distinctive value is the internal-consistency audit (risk contradiction, Composite geometry, the LLM-leak overstatement, accumulation's missing exits) — which is also what made two of R2's suggestions unsafe to adopt as written. Merged with the conflicts resolved, the plan above is the complete punch list: nothing in either review is dropped, everything is either adopted, sequenced behind a dependency, evidence-gated, or explicitly rejected with the reasoning shown.
