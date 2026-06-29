# Plutus — Design Review

A critical read of `PLUTUS_ENGINE.md` from the seat of someone who actually swings size in NSE cash and has been burned by every shortcut in here. The tone is blunt on purpose. The system is good; that's exactly why the remaining holes matter.

---

## 0. Bottom line up front

Plutus is in the top decile of personal trading systems I've seen on paper. The architecture is right where it counts: a **deterministic, back-testable score that the LLM is not allowed to vote on**, ATR-anchored sizing, regime gating, and a closed outcome loop with MFE/MAE. Most retail "AI trading" projects die on exactly these points and Plutus gets them right.

But the document oversells the *edge* and undersells the *leaks*. In its current form I'd expect live results to land well below the backtested numbers for four reasons that compound:

1. **No transaction-cost / slippage / gap modeling** anywhere. Every backtested Sharpe and expectancy in the system is optimistic by an unknown but non-trivial amount.
2. **The "best-Sharpe-of-7-bundles on a 90-day per-stock window" selection is statistically broken** — it's selecting the luckiest estimator out of seven on tiny samples, then *also* feeding that lucky number back into the score. Double overfitting.
3. **No benchmark.** Nothing in the design measures whether the picks beat just buying NiftyBeES. A long-only book of up to 10 correlated names in a bull market is mostly leveraged beta wearing a stock-selection costume, and the system can't tell the difference.
4. **Several "discipline" numbers are internally inconsistent or geometrically self-defeating** (the 2% vs 5% risk contradiction; Trend bundle's T1 R:R is *below* the 1.5× floor the whole system is built around; the Composite bundle combines the tightest stop with the nearest target and calls it high conviction).

None of these are fatal. All are fixable. Priorities are in §4. The component-by-component teardown is §3.

---

## 1. What's genuinely good (don't break these)

Keeping this short because you asked for criticism, but these are load-bearing and worth protecting:

- **LLM is fenced out of the decision.** The score is arithmetic; the LLM writes prose. This is the single most important correct call in the whole design. (Caveat in §3.10 — it's not as clean as the doc claims, but the *intent* is right.)
- **ATR-anchored position sizing.** Correct. Flat-rupee sizing is the #1 silent killer of retail books and you've designed it out.
- **Outcome tracker with MFE/MAE, tagged by bucket/bundle/regime.** This is the part almost nobody builds. It's what will eventually tell you the truth. Protect it.
- **Hard R:R floor as a discipline lever.** Right instinct. (The *implementation* has a bug — §3.6.)
- **Dual-mode capital separation with no shared budget.** Thoughtful. Stops the classic "I'll just average down my swing trade into an investment" rationalization.
- **Insufficient-data guard, walk-forward OOS gate, one-knob-per-week conservative auto-tune.** Good engineering hygiene. The RELIANCE Sharpe −93 anecdote tells me you've already been bitten and built a guard. Good.
- **The "tell the user *why* there are 0 signals" UX.** Underrated. Empty tables make people override systems.

The honesty of §16 and §17 is also genuinely good — but §16 still overstates the edge. See §3.16.

---

## 2. The four structural problems (cross-cutting, ranked by damage)

These aren't about any one module. They're properties of the whole system and they're the things most likely to make live ≠ backtest.

### 2.1 No cost model — everything downstream is optimistic

There is not a single mention of STT, brokerage, exchange transaction charges, GST, stamp duty, or **slippage**. For NSE cash delivery swing trades, round-trip frictional cost is roughly 0.2–0.5%+ depending on broker and whether you're hitting delivery STT (0.1% each side) vs intraday. Slippage on midcaps at size adds more.

Why this is structural and not a nitpick: your targets are ATR-multiples. If a midcap's daily ATR is ~2% of price, a "+2×ATR" T1 is a ~4% gross move. Bleed 0.4% round-trip and you've lost 10% of the gross reward on every winning trade — and you pay the friction on losers too. A backtest that books the clean `entry → target` and `entry → stop` prices with zero cost will show an expectancy that **does not exist** at the broker. The whole pitch of Plutus is "back-testable arithmetic." Cost-free arithmetic is the wrong arithmetic.

**Fix:** put a cost-and-slippage model in the backtest harness *and* in the live R:R calc. Slippage should scale with (position size ÷ 20-day ADV) and with ATR. Re-derive the R:R floor on a **net** basis — a 1.5× gross setup might be 1.3× net.

### 2.2 The bundle-selection method is overfit twice over

Three compounding issues with "seven bundles, each back-tested over rolling 90 days per stock, highest validated Sharpe seeds the plan":

- **Sample size.** 90 trading days ≈ 4.5 months. A swing bundle holding 3–10 days that only fires on a strict conditional entry will produce maybe 2–8 trades per stock in that window — often zero. Sharpe on n=4 is noise. Sharpe on n=4 is also *unstable*: one outlier flips the ranking.
- **Selection bias (the big one).** You take the **maximum** Sharpe across 7 noisy estimators. The max of 7 noise draws is biased high *by construction*. The bundle that "wins" each week is disproportionately the luckiest one, not the best one. This is the deflated-Sharpe / multiple-testing problem and it's exactly how strategies look great in-sample and die live.
- **Regime contamination + circularity.** If the last 90 days were bullish, the Trend bundle wins on nearly everything — so you're really just buying whatever recently worked, which is a momentum-of-strategies bet you didn't mean to make. And then the winning bundle's Sharpe is fed back in as 15% of the Technical pillar (§3.6), so the lucky number both *picks the plan* and *inflates the score*. Double-dip.

**Fix:**
- Back-test bundles **pooled across the universe**, not per-stock, so each bundle's stats have hundreds of trades, not four.
- Require a **minimum trade count** (e.g. ≥30 pooled) before a bundle's Sharpe is even eligible to seed a plan.
- Rank by a **deflated Sharpe ratio** or shrink each bundle's Sharpe toward a pooled prior. Don't rank raw maxima.
- Decouple plan-selection from scoring: the bundle that seeds the plan should not also donate its Sharpe to the score unchanged. Use the *pooled* bundle quality, not the per-stock lucky draw.

### 2.3 No benchmark = you can't prove the rubric does anything

Plutus is long-only, ~beta-1 to Nifty, up to 10 concurrent positions. In a bull run, those 10 longs are *one trade*: long Nifty with tracking error. The system measures win rate, expectancy, calibration — but never asks the only question that matters: **did the picks beat just holding the index?**

Without a benchmark you will mistake beta for alpha. A 62% win rate and positive expectancy during H1 of a bull market proves nothing if NiftyBeES did the same with no effort and no single-stock risk.

**Fix:** every postmortem must report realized swing-pool return vs:
1. **Nifty buy-and-hold** over the same dates (beta baseline), and
2. **A random-liquid-stock baseline** — same number of trades, same hold windows, random entries from the universe (selection-skill baseline).

If Plutus doesn't beat both, the rubric is decoration. This is the highest-value measurement you're missing and it's cheap to add.

### 2.4 Internal contradictions and self-defeating geometry

Three concrete bugs, not opinions:

- **2% vs 5% risk.** §4 says the risk rule is "2% of swing pool per trade." §9 says `max_risk_pct` default is **5%**. Those are very different systems. At 5% risk × up to 10 positions, a correlated market gap-down can put **~50% of the pool at risk simultaneously** (and these *are* correlated — see §3.9). Pick one. I'd argue 1–2% given the correlation.
- **Trend bundle T1 fails the system's own floor.** Trend stop = −1.5×ATR, T1 = +2×ATR. R:R to T1 = 2/1.5 = **1.33×**, which is *below* the 1.5× floor the entire system is built to enforce. So is the score using T2 (3×ATR → 2.0×) for the R:R pillar? If yes, you're crediting reward you reach far less often (§3.6). If it's using T1, the bundle is mathematically un-BUY-able. This needs to be pinned down and stated.
- **Composite bundle picks the worst of both legs.** §5 Composite: "tightest of the three stops; closest of the three targets." That's the **lowest** R:R combination — highest chance of a noise stop-out, smallest reward — and it's labeled the high-conviction ensemble. High agreement should buy you *room and reward*, not the tightest stop and nearest target. This is backwards.

---

## 3. Component-by-component teardown

Following the document's own structure so nothing's skipped.

### 3.1–3.2 Concept & philosophy

The swing/accumulation split is sound and the "user is never left with do-nothing" framing is a real behavioral win. One gap: **what happens at the regime boundary to capital that's mid-flight?** If you're tranched into HDFCBANK in accumulation and the regime flips BULL, the bull-ready alert is nice, but there's no specified logic for *rebalancing the pool split* or for the swing pool suddenly wanting capital that's tied up in accumulation. Define the handoff, or you'll be capital-starved in exactly the regime where the swing engine is supposed to shine.

### 3.3 Data sources

The honest "what we don't use" section is good. Two real risks the doc glosses:

- **Corporate-action adjustment is never mentioned, and it will silently corrupt everything.** NSE has frequent bonuses/splits. If AngelOne returns one adjustment convention and yfinance (.NS) returns another, and you fall back between them across days, your EMA/ATR/Donchian series will develop phantom gaps the size of a split. yfinance Indian data specifically is notorious for bad adjustments, missing sessions, and wrong volumes. **Mixing adjusted and unadjusted sources for the same symbol is a landmine.** Pin one adjusted source per symbol; reconcile on overlap; explicitly handle ex-dates.
- **MF accumulation (Tickertape) is lagged disclosure data**, often monthly/quarterly with a reporting delay. Treating an `ACCUMULATING` verdict as a current signal can be weeks stale. Fine as a slow tailwind; dangerous if weighted like a live flow.

### 3.4 Indicators

Solid, standard set. The claim "ATR is the single most important number" is correct and well-implemented. One omission that matters for a swing system: **no volatility-regime input (India VIX).** Swing R:R is wildly different at VIX 11 vs VIX 22 — stops get hit far more often in high-vol regimes regardless of setup quality. Worth adding as a sizing/threshold modulator.

### 3.5 The seven bundles

Beyond the selection-bias problem (§2.2):

- **Stop = 1.5×ATR(daily) on a 3–10 day hold is tight and gap-exposed.** For a 2–4% daily-ATR midcap that's a ~3–6% stop, and NSE gaps on global/overnight news routinely jump *through* it — so your realized loss is worse than the planned 1.5×ATR, which quietly breaks the per-trade risk math in §9. Model gap-through-stop in the backtest or your `STOPPED` losses are understated.
- **SMC bundle is borderline pseudo-quant.** BOS/CHOCH/order-blocks have no robust out-of-sample edge in the literature and are highly discretionary to codify — every practitioner draws the order block differently. You've flagged it "experimental," which is the right call, but I'd question whether it earns a slot in the ensemble at all versus just adding correlated noise.
- **VCP** is a reasonable proxy ("each ATR-corrected contraction smaller than the last") but it'll be rare and late, and Minervini's edge was a *whole-market-leader ranking system*, not a single-stock pattern. Don't expect the pattern alone to carry it.
- **PEAD** depends on accurate earnings dates, which you flag — but free NSE earnings-date data is genuinely unreliable, and PEAD's edge has decayed in liquid names and is *extremely* cost-sensitive (small drift, high friction → §2.1). This may be a net-negative bundle after costs.
- **Composite stop/target logic is backwards** (§2.4).

### 3.6 Swing scoring rubric

The deterministic-rubric-over-LLM rationale (§6 "Why this design") is the best-argued part of the document and I fully agree with it. Problems are in the pillar mechanics:

- **R:R pillar credits geometry, not expectancy.** Scoring R:R as a static distance ratio (1.5×→0, 2.5×→100) rewards *wider targets* regardless of how often they're reached. A 3:1 setup hit 20% of the time is worse than a 1.5:1 hit 55% of the time, but the rubric scores the 3:1 higher. The reachability of an ATR-multiple target is not linear in the multiple. **Use probability-weighted expectancy** (from the bundle's *pooled* realized hit-rate at that target), not raw ratio. And reconcile which target the ratio uses given the T1-below-floor issue (§2.4).
- **Smart Money pillar is mostly not stock-specific.** FII/DII net cash is **one market-wide number** applied identically to every candidate — it gives zero cross-sectional discrimination and just shifts all scores together, i.e. it's a *regime* input double-counted into a "smart money" pillar (which already overlaps the Regime pillar). The only stock-specific piece (MF accumulation) is lagged disclosure data (§3.3). So 15% of the score leans on a market-wide number plus stale monthly data. **Cut this pillar's weight, or replace FII/DII with something actually per-stock** (e.g. delivery % / delivery-volume trends from NSE bhavcopy, bulk/block deals).
- **Sentiment hard-kill is high-variance.** A keyword-tier classifier on thin NewsAPI coverage of Indian midcaps will mis-tag. Turning a single noisy "material negative" match into score 0 + hard-avoid means one bad keyword hit kills a good setup. **Make it a graded penalty unless corroborated** (two independent headlines, or price/volume confirmation). Reserve the hard-kill for unambiguous events (results, rating action) you can verify structurally.
- **Expected win-rate per bucket — where does "expected" come from?** If the pillar weights were hand-set, the "expected 60% for bucket 70–80" is an *assumption*, and the calibration loop's "divergence" might just be a regime shift, not rubric drift (§3.13).

### 3.7 Accumulation rubric

- **No exit logic and no thesis-invalidation.** "Rarely a single hard SL," "through drawdowns," exit only via bull-ready re-score. This is how you end up holding a value trap for 18 months. There's no max-loss, no time-stop, and **the hard-avoid checks (debt, earnings collapse) only fire at initial scoring, not at each tranche.** Add a fundamental-deterioration exit: if D/E spikes past the avoid threshold or EPS growth turns sharply negative *after* you're in, you exit even at a loss. "Accumulate forever" is not a strategy.
- **Tranche triggers are fixed % and volatility-blind.** −8% / −15% means very different things on a low-vol FMCG name vs a high-beta smallcap. **Normalize triggers by the stock's ATR/volatility.** And critically — **re-validate the fundamental thesis at each tranche.** Averaging down on a fixed price schedule regardless of *why* it dropped is the textbook way to throw good money after bad.
- **Valuation pillar = P/E vs sector median** is crude (cyclicals look "cheap" at peak earnings, "expensive" at the trough — P/E inverts the signal exactly when it matters). Consider a blend or at least a cyclicality guard.

### 3.8 Regime detector

Single classifier on Nifty 50-EMA price+slope. Two issues:

- **It lags major turns by weeks and whipsaws at the boundary.** 50-EMA crossovers are late by design; the ~2% band reduces but doesn't fix the chatter. A regime that's 4–6 weeks late means the swing engine keeps firing into the first leg of a bear and the accumulator starts late. **Add breadth** (% of stocks above their 200-DMA, advance/decline) — breadth *leads* the index at turns — **and India VIX** for the volatility dimension. A breadth-confirmed regime flips earlier and whipsaws less.
- Regime is one Nifty number, but you trade single stocks across 12 sectors. A stock in a top-3 RS sector can be in its own bull while Nifty is SIDEWAYS. The sector-RS sub-score helps, but consider a per-stock or per-sector trend gate in addition to the index gate.

### 3.9 Risk manager

- **Portfolio risk ignores correlation.** The per-trade caps are fine in isolation, but 10 long swing positions in a bull market are ~one leveraged Nifty bet. "Max risk per trade × N positions" *understates* true portfolio risk because a market gap-down hits all stops together. **Add a correlation-aware portfolio-heat cap** (sum of position risks, haircut for average pairwise correlation) and reconcile the 2%/5% contradiction downward.
- **No drawdown governor.** Nothing throttles size or position count after a losing streak or a pool drawdown. Add a circuit-breaker: e.g. cut per-trade risk in half after the pool is −X% from its high-water mark, restore on recovery. This is cheap insurance against a bad regime call.
- **No liquidity-at-size cap.** Risk-cap sizing can spit out a share count that's large vs a midcap's ADV → slippage on the way in *and* the way out (and you can't always get out). Cap position at, say, ≤10–15% of 20-day ADV.

### 3.10 Agent graph — the "no LLM leak" claim is overstated

The intent is right and the separation is cleaner than most. But the doc's "the recommendation comes from arithmetic, not from a sentence" is **not fully true as drawn:**

- The `sentiment (LLM)` node writes the material-event flag → which can trigger the **hard-avoid** → which forces AVOID. That's an LLM flipping the classification.
- The `smart_money (LLM)` node writes the verdict that feeds the Smart Money pillar.
- The `technical (LLM)` node writes entry/stop/T1/T2, which the R:R pillar and risk manager consume.

So LLM-extracted features absolutely enter the deterministic score. The arithmetic is clean; its *inputs* are LLM-generated and can be wrong. Also note an **internal inconsistency**: §4/§6 describe sentiment as a *deterministic keyword-tier* score, while §10 has an *LLM* sentiment node. Which one feeds the score? If both, that's two sources of truth for the same pillar.

**Fix:** for anything that can flip a classification (sentiment material-event flag, smart-money verdict), make the extraction **deterministic and rule-based** (you already have the keyword tiers). Keep the LLM strictly for the narrative and for *non-gating* color. Then the "no LLM leak" claim becomes actually true.

### 3.11 Backtesting harness

- The insufficient-data guard and walk-forward OOS gate are good.
- **Execution-timing assumption is unstated and it's the whole ballgame.** Entry rules trigger on "today's close > EMA20" etc. You cannot transact at the close you used to trigger. If the backtest enters at the *same* close, it has look-ahead. Confirm entries are simulated at **next-bar open** (with slippage), and that live execution matches.
- **Survivorship/point-in-time:** is the "liquid universe" defined as-of-today or point-in-time per backtest date? If today's liquid names, you're testing on survivors → upward bias. Use point-in-time universe membership.
- **The backtested plan must equal the executed plan.** The best-Sharpe bundle is back-tested with *its own* stop/target, but live the plan may be adjusted by the Composite/risk-manager. If the executed stop ≠ the backtested stop, the backtested edge doesn't transfer.
- Sharpe is the wrong headline metric at these sample sizes (§3.12).

### 3.12 Outcome tracker

The best-built module. MFE/MAE tagged by bucket/bundle/regime is exactly right. One reframing:

- **Stop reporting win rate as a headline.** Win rate is a vanity metric — 40% at 3:1 beats 65% at 1:1. Lead with **expectancy and profit factor, with confidence intervals.** This also matters for the tuning loop (§3.13), which currently optimizes toward win rate and could therefore push the system toward lower-expectancy, higher-hit-rate trades — the wrong direction.

### 3.13 Self-finetuning loop

Right instinct (suggest, log, survive being wrong), wrong statistics:

- **Sample sizes don't support the claims.** ≥30 trades per bucket sounds disciplined but a 95% CI on a 60% win rate at n=30 is roughly **±18 percentage points** — wider than the 15pp divergence that triggers a suggestion. So the trigger fires on noise. Same for "rollback if win rate drops >5pp over 4 weeks" — 4 weeks of swing trades is a handful of samples.
- **Multiple testing.** You're watching many cells (buckets × bundles × regimes). With enough cells, *something* will cross 15pp for 2 weeks by chance every month. Without a correction you'll generate a steady stream of false "drift detected" suggestions.
- **Confounding with regime.** A bucket's realized win rate is a mixture across regimes; a flip in the regime mix looks like rubric drift. Tuning weights in response will overfit to the *recent* regime and hurt when it turns.

**Fix:** require larger pooled n, report CIs on every divergence, apply a multiple-testing correction (or just raise the bar substantially), and condition calibration on regime before flagging drift. Optimize the loop toward **expectancy**, not win rate.

### 3.14 Alerts

Mostly fine. One gap: **trend-invalidation only fires after a position is "held > 5 days."** Days 1–5 have *no* exit except the 1.5×ATR stop. A trade can drift sideways-to-down for a week, never hit the stop, and rot. Add a **time/no-progress exit** for the early window (e.g. "if not at +0.5×ATR by day N, flat it").

### 3.15 Weekly cadence

- **Weekend gap risk.** Screening Sunday on Friday's close and entering Monday means weekend/global news can invalidate the setup before you're in. The Monday 09:10 re-validation helps — make sure it actually re-runs the entry gates against Monday's open, not just updates status.
- **Weekly cadence structurally misses time-sensitive bundles.** A breakout or PEAD setup that triggers Wednesday is stale by the next Sunday screen. If you're keeping Breakout/PEAD, they need a higher-frequency screen or they'll mostly fire late. (Or accept that those two bundles underperform and weight accordingly.)

### 3.16 Where the edge comes from — honest, but still overstated

§16 is the most honest "edge accounting" I've read in a retail doc, and points 1, 2, 4, 6 (discipline, ATR sizing, regime gating, closed loop) are real. But:

- Point 3 ("bundle ensemble → higher win rate") is undermined by the selection bias in §2.2 — the ensemble as built is partly selecting noise.
- Point 7 ("no leak from LLM") is overstated (§3.10).
- The biggest unstated caveat: **most of the swing edge claimed here is behavioral, not predictive.** The real, durable edge is points 1, 2, 4, 6 — *not losing* via discipline, sizing, and regime-avoidance. That's worth a lot! But it's a different claim from "the rubric picks winners," and the system currently can't distinguish them because there's no benchmark (§2.3). Be honest in the doc about which edge is which.

### 3.17–3.19 Scope, dashboard, philosophy

The "does NOT do" section and the regime-color-always-visible UX are good. The closing "make the decision boring and the execution disciplined" thesis is the correct soul of the project — keep it. Just make sure the *measurements* (benchmark, expectancy, costs) are honest enough to tell you when the boring decision is also a losing one.

---

## 4. Prioritized roadmap

Ordered by impact-per-effort. Do the top three before you trust a single backtest number.

**P0 — do these first, they change what the numbers mean**
1. **Add a cost + slippage + gap model** to the backtest harness and the live R:R calc. Re-derive the R:R floor on a net basis. (§2.1)
2. **Fix bundle selection:** pool backtests across the universe, require min trade count, rank by deflated/shrunk Sharpe, and stop feeding the lucky per-stock Sharpe back into the score. (§2.2, §3.6)
3. **Add the two benchmarks** (Nifty buy-and-hold + random-liquid baseline) to every postmortem. (§2.3)

**P1 — fixes contradictions and the worst risk holes**
4. Reconcile **2% vs 5%** risk and add a **correlation-aware portfolio-heat cap** + **drawdown governor** + **ADV size cap**. (§2.4, §3.9)
5. Resolve the **Trend T1 < floor** and **Composite tightest-stop/nearest-target** geometry bugs; switch the R:R pillar to **probability-weighted expectancy**. (§2.4, §3.6)
6. Make **classification-flipping inputs deterministic** (sentiment material-event flag, smart-money verdict); demote sentiment hard-kill to a corroborated penalty; resolve the dual sentiment-path inconsistency. (§3.6, §3.10)

**P2 — accuracy and honesty of the measurement loop**
7. **Harden data:** one adjusted source per symbol, corporate-action handling, no mixing adjusted/unadjusted. (§3.3)
8. **Accumulation exits:** thesis-invalidation exit, re-validate fundamentals at each tranche, volatility-normalize triggers. (§3.7)
9. **Confirm execution timing** (next-bar open, no look-ahead) and **point-in-time universe** in the harness. (§3.11)
10. **Tuning-loop statistics:** CIs, multiple-testing correction, regime-conditioning, optimize expectancy not win rate. (§3.12, §3.13)

**P3 — edge improvements**
11. Upgrade the **regime detector** with breadth + India VIX. (§3.8)
12. Add a **time/no-progress exit** for the early swing window. (§3.14)
13. Reconsider whether **SMC** and post-cost **PEAD** earn their ensemble slots. (§3.5)
14. Add **per-stock smart-money** signals (delivery %, bulk/block deals) to replace the market-wide FII/DII in the Smart Money pillar. (§3.6)

---

## 5. One thing to internalize

Your doc's closing line is right: make the decision boring and the execution disciplined. The risk is that "boring and disciplined" quietly becomes "confidently wrong" if the measurement layer flatters itself. The three P0 items — costs, honest bundle stats, and a benchmark — are what convert this from *a system that looks good in a notebook* into *a system you can tell whether to trust*. Everything else in here is refinement on a genuinely strong foundation.
