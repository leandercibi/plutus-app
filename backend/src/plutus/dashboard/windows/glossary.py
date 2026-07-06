from __future__ import annotations

import streamlit as st

from plutus.dashboard.theme import (
    BUY_GREEN,
    DEAD_ZONE,
    DEAD_ZONE_BG,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)

# ---------------------------------------------------------------------------
# Term definitions
# ---------------------------------------------------------------------------

_TERMS: list[dict] = [
    # --- Accumulation ---
    {
        "name": "RS 30 / 90 / 180",
        "category": "accumulation",
        "one_liner": "How much more (or less) a stock returned vs Nifty 50 over the last 30, 90, and 180 trading days.",
        "detail": (
            "RS 30 = +5 % means the stock gained 5 percentage points more than Nifty over the past month. "
            "The three numbers give you short-, medium-, and long-term momentum snapshots."
        ),
        "analogy": (
            "Think of it like comparing a student's grades against the class average — for last month's test (RS 30), "
            "last quarter (RS 90), and the full semester (RS 180). A student who is above average across all three "
            "periods shows genuine ability. One who aced last month but was below average all semester is probably just having a good day."
        ),
        "example": "RS 30 = +8 %, RS 90 = +5 %, RS 180 = +3 % → the stock has been outperforming consistently and accelerating. "
        "RS 30 = +8 %, RS 90 = -2 %, RS 180 = -4 % → a one-month bounce, not a trend.",
        "how_to_use": (
            "All three positive → institutions are likely accumulating. Start watching for a tranche entry. "
            "RS 30 positive but RS 90/180 negative → wait. This is a bounce, not a trend. "
            "All three negative → the stock is underperforming even if it looks 'cheap'. "
            "Relative weakness usually continues."
        ),
    },
    {
        "name": "RS Blend (RS Pillar, 0–15)",
        "category": "accumulation",
        "one_liner": "A single 0–15 score that combines RS 30/90/180 with more weight on longer horizons.",
        "detail": (
            "Blend = 0.2 × RS30 + 0.4 × RS90 + 0.4 × RS180. Longer time horizons get more weight because short-term "
            "outperformance is easy to fake (one news event, one large trade). Six-month persistence is harder to manufacture."
        ),
        "analogy": (
            "Like judging a marathon runner. A fast sprint at km 1 (RS 30) is impressive but tells you little. "
            "Consistent pace across the full 42 km (RS 180) is what separates serious runners from weekend joggers. "
            "The blend score rewards the full-race performance."
        ),
        "example": "RS 30 = +10 %, RS 90 = +6 %, RS 180 = +4 % → blend ≈ +6 %. Normalized to 15-point scale → RS Pillar ≈ 9. "
        "RS 30 = +15 %, RS 90 = -3 %, RS 180 = -5 % → blend ≈ -0.2 %, RS Pillar ≈ 0.",
        "how_to_use": (
            "RS Pillar ≥ 10/15 → consistent outperformer, worth accumulating. "
            "RS Pillar < 5 → lagging the index at every horizon. Even if cheap, relative weakness often continues. "
            "An ACCUMULATE_NOW rating needs total ≥ 75 — so RS Pillar of 12+ gives you a meaningful head start."
        ),
    },
    {
        "name": "Quality Pillar (0–30)",
        "category": "accumulation",
        "one_liner": "How good the business fundamentals are — ROCE (profitability), D/E (leverage), and FCF margin (cash generation).",
        "detail": (
            "Quality = score(ROCE) + score(D/E) + score(FCF margin). Each component is scored individually and summed. "
            "A great business earns high returns on capital, isn't drowning in debt, and actually converts profit into cash."
        ),
        "analogy": (
            "Rating a restaurant: ROCE = how much the kitchen earns vs what was invested in it (equipment, rent). "
            "D/E = how much of the restaurant was bought with loans vs the owner's own money. "
            "FCF = whether the cash register actually fills up at day's end, not just the accounting ledger. "
            "A great restaurant has a packed kitchen, owns the property outright, and has cash in the till."
        ),
        "example": "ROCE = 28 %, D/E = 0.2, FCF margin = 18 % → Quality ≈ 27/30 (excellent compounder). "
        "ROCE = 10 %, D/E = 1.8, FCF margin = 3 % → Quality ≈ 12/30 (mediocre, borderline).",
        "how_to_use": (
            "Quality ≥ 22 is required for ACCUMULATE_NOW — it's a hard floor. "
            "Quality 22–25 = decent business, an acceptable candidate. "
            "Quality 27–30 = true compounder. These are the ones worth holding through corrections. "
            "If Quality < 18, don't accumulate regardless of how cheap it looks. A bad business stays bad."
        ),
    },
    {
        "name": "Growth Pillar (0–25)",
        "category": "accumulation",
        "one_liner": "How fast earnings per share (EPS) have been compounding — penalises base-effect spikes.",
        "detail": (
            "Scores the 3-year and 5-year CAGR of EPS. 'Base-effect spikes' (e.g. EPS went from ₹0 to ₹10 after a loss year) "
            "are excluded because they aren't real growth — just recovery. Steady compounding year after year scores better."
        ),
        "analogy": (
            "Imagine two employees' salary growth. Employee A: ₹5L → ₹6L → ₹7L → ₹8L → ₹9L (steady 15% raise). "
            "Employee B: ₹5L → ₹1L (bad year) → ₹5L → ₹5L → ₹5L (just recovered). "
            "Employee B's '400% growth' in year 2 is meaningless — it's just getting back to baseline. "
            "The system ignores that spike and rewards Employee A."
        ),
        "example": "EPS CAGR 3y = 18 %, 5y = 15 % → Growth ≈ 20/25. "
        "EPS CAGR 3y = 5 %, 5y = 2 % → Growth ≈ 6/25 (stagnant).",
        "how_to_use": (
            "Growth 20–25 = strong compounder. Pair with Quality 25+ for a rare 'buy and hold forever' candidate. "
            "Growth 10–15 = decent, still accumulate-worthy if Quality and Valuation compensate. "
            "If 5y CAGR is high but 3y CAGR is low, growth is decelerating — be cautious. "
            "A declining CAGR often precedes earnings disappointments."
        ),
    },
    {
        "name": "Valuation Pillar (0–30)",
        "category": "accumulation",
        "one_liner": "How cheap the stock is vs its own historical PE — not vs peers, not vs the index.",
        "detail": (
            "Compares current PE TTM to its 5-year median PE. If the stock normally trades at PE 30 and is now at PE 20, "
            "it's at a 33% discount — high valuation score. If it's at its usual PE or above, score is 0. "
            "Currently often shows 0 because 5-year historical PE is unavailable from free data sources."
        ),
        "analogy": (
            "A Zara shirt you always buy for ₹3,000. Today it's ₹1,800 in a sale — you know it's cheap because you know the "
            "normal price. Now imagine buying a shirt you've never seen before for ₹1,800 — you have no idea if that's cheap or expensive. "
            "Without historical PE data, every stock is the 'new shirt'. That's why Valuation is often 0."
        ),
        "example": "Normal PE = 35, current PE = 20 → 43% discount → Valuation ≈ 25/30. "
        "Normal PE = 30, current PE = 32 → slight premium → Valuation = 0.",
        "how_to_use": (
            "Don't penalise a stock for Valuation = 0 — it means 'unknown', not 'expensive'. "
            "A non-zero Valuation score is a genuine signal that the stock is trading below its historical norm. "
            "Combine with Quality and Growth to identify 'quality-on-sale' setups — these are the best risk/reward. "
            "Never buy a low-Quality stock just because Valuation is high."
        ),
    },
    {
        "name": "ACCUMULATE_NOW / BUILD_SLOWLY / WATCH / AVOID",
        "category": "accumulation",
        "one_liner": "The classifier label summarising whether to actively buy, cautiously buy, monitor, or skip.",
        "detail": (
            "ACCUMULATE_NOW: total pillar score ≥ 75 AND Quality ≥ 22. Both conditions required. "
            "BUILD_SLOWLY: total 60–74. Good business, but signals aren't all aligned yet. "
            "WATCH: total < 60. Interesting but not ready — revisit after the next pipeline run. "
            "AVOID: a Hard Avoid flag fired (excessive debt, EPS collapse, etc.)."
        ),
        "analogy": (
            "Like a traffic light but for stock entry. Green (ACCUMULATE_NOW): conditions are right, go. "
            "Yellow (BUILD_SLOWLY): proceed slowly, don't go all-in. "
            "Red (WATCH/AVOID): stop and wait. "
            "The key difference from ordinary traffic lights: you can wait as long as you want for green."
        ),
        "example": "HDFCBANK: Quality 27, Growth 18, Valuation 0, RS Blend 12 → total 57 → WATCH (Valuation holding it back). "
        "If Valuation data becomes available and it scores 15 → total 72 → BUILD_SLOWLY.",
        "how_to_use": (
            "ACCUMULATE_NOW + RS Pillar ≥ 10 + Quality ≥ 25 = highest conviction → start with tranche 1. "
            "BUILD_SLOWLY → fine for tranche 1 if you have personal conviction in the thesis, but size down. "
            "WATCH → do your own research; don't start a position just because it's in the list. "
            "AVOID → respect the Hard Avoid. These flags exist because the thesis is already broken."
        ),
    },
    {
        "name": "Tranche",
        "category": "accumulation",
        "one_liner": "One of up to 5 partial buy orders that build a position over time as the price dips.",
        "detail": (
            "Instead of buying the full position at once (risky if the stock keeps falling), you buy 20% at a time "
            "across 5 tranches. Each subsequent tranche is triggered when the stock drops by ~1.5–5× ATR from the previous buy. "
            "This averages down your cost and spreads risk over time."
        ),
        "analogy": (
            "Like filling a swimming pool during a drought. Instead of turning on the tap at full blast and hoping the water "
            "level is right, you add water in 5 measured pours whenever the pressure is good (price is lower). "
            "You never know where the exact bottom is, so you spread your bets. "
            "Each pour lowers your average 'fill cost'."
        ),
        "example": "Tranche 1: buy at ₹1,000. Stock drops to ₹960. Tranche 2: buy at ₹960. Average cost = ₹980. "
        "Stock drops to ₹910. Tranche 3: ₹910. Average cost = ₹957. Now waiting for either tranche 4 or a rally.",
        "how_to_use": (
            "Use the tranche trigger price the system suggests (based on ATR). Don't rush to fill all 5. "
            "If the stock rallies after tranche 1 and you miss tranches 2–5, that's fine — tranche 1 is profitable. "
            "If the stock keeps falling but Hard Avoid fires, pause or exit. Never add tranches to a broken thesis."
        ),
    },
    {
        "name": "Hard Avoid",
        "category": "accumulation",
        "one_liner": "Automatic disqualifiers that block accumulation regardless of how good other scores look.",
        "detail": (
            "Current flags: D/E > threshold (excessive debt for non-financial companies), EPS collapsed > 50 % YoY "
            "without improving guidance, going-concern audit note, promoter pledge jumped > 10 percentage points. "
            "Even a Quality-30 business is disqualified if any hard avoid fires."
        ),
        "analogy": (
            "Like a job application. Even a brilliant candidate gets rejected if they have certain red flags on their background check "
            "(fraud conviction, false credentials). These aren't soft concerns — they're absolute disqualifiers "
            "because the downside risk is too high to justify the potential upside."
        ),
        "example": "A pharma company with ROCE 25%, D/E 0.2, EPS CAGR 20% — all great. "
        "But last quarter EPS dropped 65% YoY. Hard Avoid fires. "
        "Reason: a single catastrophic quarter can signal FDA issues, patent cliff, or fraud.",
        "how_to_use": (
            "Respect the flag. Don't manually override without specific knowledge. "
            "D/E breach: check if it's temporary (acquisitions) or structural (operational losses). "
            "EPS collapse: check if it's a one-time write-off or a sustained decline. "
            "If you're confident it's a one-time event, the Hard Avoid badge will disappear once next quarter's data loads."
        ),
    },
    {
        "name": "CAGR EPS (3y / 5y)",
        "category": "accumulation",
        "one_liner": "Compound Annual Growth Rate of Earnings Per Share — how fast per-share profits have grown.",
        "detail": (
            "If EPS was ₹10 five years ago and is ₹16.1 today, 5y CAGR = 10% (because ₹10 × 1.10⁵ ≈ ₹16.1). "
            "It compounds, so even moderate rates (10–15%) create large absolute gains over time."
        ),
        "analogy": (
            "Like a salary raise: 12% CAGR means your ₹10L salary becomes ₹17.6L in 5 years and ₹31L in 10 years. "
            "A company growing EPS at 20% CAGR doubles its per-share earnings in under 4 years. "
            "At that rate, even paying a high PE today can be justified — you're buying tomorrow's earnings."
        ),
        "example": "CAGR 3y = 22%, CAGR 5y = 18% → accelerating growth, excellent signal. "
        "CAGR 3y = 5%, CAGR 5y = 18% → growth is decelerating badly, despite good history.",
        "how_to_use": (
            "Look at both numbers together. If 5y > 3y, growth is slowing — reduce conviction. "
            "If 3y > 5y, growth is accelerating — increase conviction. "
            "The Growth Pillar score already encodes this, so a high Growth score means both are solid. "
            "Any CAGR below 0 means earnings are shrinking — likely triggers Hard Avoid."
        ),
    },
    {
        "name": "ROCE (Return on Capital Employed)",
        "category": "accumulation",
        "one_liner": "How much operating profit the business generates for every rupee of capital invested in it.",
        "detail": (
            "ROCE = EBIT ÷ Capital Employed. Capital Employed = Total Assets − Current Liabilities. "
            "A ROCE of 25% means the business earns ₹25 in operating profit for every ₹100 of capital deployed. "
            "In Plutus, ROE from yfinance is used as a proxy since exact ROCE requires balance sheet decomposition."
        ),
        "analogy": (
            "Like yield on investment property. If you invest ₹1 crore in a shop and it earns ₹25L per year in rent, "
            "your yield is 25% — excellent. If it only earns ₹8L, yield is 8% — barely above inflation. "
            "High ROCE businesses earn well above their cost of capital, creating real wealth."
        ),
        "example": "ROCE 30%: for every ₹100 the company uses, it makes ₹30 profit. "
        "After accounting for 10% cost of capital, it creates ₹20 of value. This is rare and precious.",
        "how_to_use": (
            "ROCE > 20% = high quality business, strong Quality Pillar score. "
            "ROCE 12–20% = decent, acceptable. Below 12% = mediocre or capital-intensive. "
            "Compare ROCE to the company's own history — a ROCE that's falling (even from a high base) "
            "suggests the business is maturing or facing competition."
        ),
    },
    {
        "name": "D/E Ratio (Debt to Equity)",
        "category": "accumulation",
        "one_liner": "How much of the business is funded by debt vs shareholder equity. Lower is safer.",
        "detail": (
            "D/E = Total Debt ÷ Total Equity. D/E = 2.0 means ₹2 borrowed for every ₹1 of owner's money. "
            "Financial companies (banks, NBFCs) have high D/E by design — deposits are 'debt' — so the Hard Avoid "
            "check is skipped for them. For non-financials, D/E > 1.5 triggers Hard Avoid."
        ),
        "analogy": (
            "Buying a house. D/E = 0.3 → you paid 77% cash, 23% mortgage — very safe. "
            "D/E = 3.0 → you paid 25% cash, 75% mortgage. Fine when property values are rising, "
            "catastrophic if prices fall and the bank calls the loan. "
            "High-D/E businesses operate like overleveraged homeowners in a downturn."
        ),
        "example": "D/E 0.1 (Infosys-like) = pristine balance sheet. D/E 0.8 = manageable. D/E 2.5 = high risk.",
        "how_to_use": (
            "D/E > 1.5 for non-financials → Hard Avoid fires. Don't invest. "
            "D/E 0.5–1.5 → look at interest coverage (can they service the debt?). "
            "D/E < 0.3 → debt is negligible. Company can fund growth internally. "
            "Watch D/E trend, not just the current number — rising D/E while earnings are flat is a warning sign."
        ),
    },
    {
        "name": "FCF Margin (Free Cash Flow Margin)",
        "category": "accumulation",
        "one_liner": "How much real cash the business generates for every rupee of revenue, after all expenses and investments.",
        "detail": (
            "FCF = Operating Cash Flow − Capital Expenditure. FCF Margin = FCF ÷ Revenue. "
            "A 15% FCF margin means for every ₹100 of revenue, ₹15 ends up as actual cash the company can use freely. "
            "Accounting profit can be manipulated; cash flow is harder to fake."
        ),
        "analogy": (
            "Like a restaurant's take-home pay. Revenue = total bills collected. FCF Margin = "
            "what's left after paying cooks, waiters, rent, and replacing broken equipment. "
            "A restaurant earning ₹10L/month but spending ₹9.8L on expenses has only ₹20K free cash — very fragile. "
            "One spending ₹7L and keeping ₹3L as FCF (30% margin) is a cash machine."
        ),
        "example": "Revenue ₹1,000 Cr, FCF ₹150 Cr → FCF margin 15% (healthy). "
        "Revenue ₹1,000 Cr, FCF ₹20 Cr → FCF margin 2% (borderline, capital-heavy).",
        "how_to_use": (
            "FCF margin > 12% = strong cash generation, comfortable Quality score. "
            "FCF margin 5–12% = acceptable for capital-intensive industries. "
            "FCF margin < 5% = fragile business. Any revenue slowdown could turn FCF negative. "
            "High profit but low FCF often means the company is burning cash on working capital or capex — "
            "investigate before accumulating."
        ),
    },
    {
        "name": "PE TTM (Price to Earnings, Trailing 12 Months)",
        "category": "accumulation",
        "one_liner": "Stock price ÷ earnings per share over the last 12 months. How many years of current earnings you're paying for.",
        "detail": (
            "PE of 30 means you're paying ₹30 for every ₹1 the company earns today. "
            "At PE 30 with zero growth, you recoup your investment in 30 years — a bad deal. "
            "At PE 30 with 25% EPS growth, you recoup much faster because earnings double every 3 years."
        ),
        "analogy": (
            "Like paying for a food stall. If it earns ₹1 lakh/year and you pay ₹15 lakh (PE=15), "
            "you recoup in 15 years. If you expect earnings to double in 3 years, "
            "you'll recoup in ~8 years — makes sense. "
            "PE alone tells you the 'sticker price'. Growth tells you if the sticker price is fair."
        ),
        "example": "PE = 40 with 30% EPS growth: PEG ratio = 40/30 = 1.3 (fair). "
        "PE = 15 with 0% EPS growth: PEG = 15/0 = infinite (cheap but going nowhere).",
        "how_to_use": (
            "Use PE TTM in context of EPS CAGR. Never say 'it's cheap at PE 12' without checking if earnings are growing. "
            "The Valuation Pillar compares PE TTM to 5y median PE — that context matters more than the absolute number. "
            "Financial companies: use P/Book instead of PE for comparability. "
            "Current PE vs 5y median is the key comparison — stock at PE 20 when it normally trades at PE 35 is genuinely cheap."
        ),
    },
    # --- Swing Trading ---
    {
        "name": "Bundle (Swing Strategy)",
        "category": "swing",
        "one_liner": "A named set of rules that screens for stocks with a specific chart or fundamental pattern.",
        "detail": (
            "Each bundle is a distinct strategy with its own signal logic, scoring criteria, and historical performance. "
            "Trend: stocks in strong uptrends. Breakout: stocks breaking through resistance. "
            "Reversal: oversold stocks bouncing. VCP: tightly coiling stocks before breakout. "
            "Composite: requires 2+ bundle signals to agree — higher conviction, lower frequency."
        ),
        "analogy": (
            "Like different fishing techniques. Trend fishing = trolling with big lures in open water (catches often). "
            "VCP fishing = fly-fishing in a specific stream (fewer catches, but each one is quality). "
            "Reversal fishing = ice fishing — high effort, risky, works in specific conditions. "
            "Each technique suits different market conditions."
        ),
        "example": "BULL regime: Trend and VCP historically have highest expectancy. "
        "SIDEWAYS regime: all bundles downgrade signals to WATCH automatically.",
        "how_to_use": (
            "Check the Calibration window to see which bundle has highest expectancy in the current regime. "
            "Don't cherry-pick bundles based on recent performance — use the full calibration history. "
            "VCP signals are rare (maybe 2–3 per Sunday run) but high-conviction. "
            "Composite signals require more patience but are the most reliable."
        ),
    },
    {
        "name": "1R / Risk R",
        "category": "swing",
        "one_liner": "The rupee amount you'd lose if the trade hits stop loss. All P&L is expressed as multiples of 1R.",
        "detail": (
            "If you buy at ₹1,000 with stop at ₹950, risk per share = ₹50. "
            "If you buy 100 shares, 1R = ₹5,000. "
            "Winning +2R means you made ₹10,000. Losing -1R means you lost ₹5,000. "
            "This makes all trades comparable regardless of stock price or position size."
        ),
        "analogy": (
            "Like a standard bet size in poker. 1R = your call. "
            "Winning 3R = you won 3× your bet. Losing 1R = you called and lost. "
            "Expressing all results in R lets you compare a ₹500 stock trade with a ₹5,000 stock trade fairly."
        ),
        "example": "₹5,00,000 capital × 1% risk per trade = 1R = ₹5,000. "
        "Entry ₹1,000, stop ₹950 → risk = ₹50/share. Shares = ₹5,000 ÷ ₹50 = 100 shares.",
        "how_to_use": (
            "Size every trade so that 1R = 1% of capital (default setting). "
            "Never move your stop to increase position size after entry. "
            "A T1 hit at +2R on a 1% risk position = +2% on capital. Compound this over 20 trades and it matters. "
            "Target expectancy > 0.3R per trade — that means on average you make 0.3% of capital per trade."
        ),
    },
    {
        "name": "Stop Loss",
        "category": "swing",
        "one_liner": "The price at which you exit a trade for a loss, defined before entry. Set at entry − 1.5× ATR.",
        "detail": (
            "Stop is calculated at entry − 1.5 × ATR (Average True Range). "
            "ATR represents the stock's typical daily price swing. "
            "1.5× ATR places the stop just outside 'normal noise' — you exit only if the stock moves abnormally against you."
        ),
        "analogy": (
            "Like a circuit breaker in your house. You set it to trip at a safe threshold, not at the slightest flicker. "
            "Set it too tight (1× ATR) and it trips on normal noise. "
            "Set it too loose (3× ATR) and too much damage is done before it trips. "
            "1.5× ATR is the calibrated sweet spot."
        ),
        "example": "Stock at ₹1,000, ATR = ₹40. Stop = ₹1,000 − 1.5 × ₹40 = ₹940. "
        "Normal daily range = ₹40, so ₹940 is just below that noise.",
        "how_to_use": (
            "Never widen a stop after entry. If price approaches your stop, let it trigger. "
            "Widening stops is the most common way traders turn small losses into catastrophic ones. "
            "You can trail the stop up after T1 hits (set stop to entry, risk-free). "
            "If ATR is very large (volatile stock), the stop is far away → you buy fewer shares → 1R is maintained."
        ),
    },
    {
        "name": "T1 / T2 (Targets)",
        "category": "swing",
        "one_liner": "T1 = first profit target (+2R from entry). T2 = second target (+3–4R from entry).",
        "detail": (
            "T1 is typically at a key resistance level or +2R above entry. "
            "T2 is at the next resistance or +3–4R. "
            "The system calculates these from the signal's drawn risk-reward ratio. "
            "A 2:1 RR means T1 is +2R above entry."
        ),
        "analogy": (
            "Like hiking a mountain with two summit options. "
            "T1 is the first summit — you can stop here and it's still a good day. "
            "T2 is the actual peak — riskier, longer, but the view (reward) is better. "
            "You sell half at T1 and let the rest ride to T2."
        ),
        "example": "Entry ₹1,000, stop ₹940 (1R = ₹60). T1 = ₹1,120 (+2R). T2 = ₹1,240 (+4R). "
        "At T1: sell 50%, move stop to entry (₹1,000). Remaining 50% rides to T2.",
        "how_to_use": (
            "The system marks a trade T1_HIT when price reaches T1. "
            "At that point: take partial profits, raise stop to entry (trade is now risk-free). "
            "Don't rush to T2 — let price dictate. "
            "Exit if price reverses sharply below the midpoint of entry–T1 range after T1 is hit."
        ),
    },
    {
        "name": "ATR (Average True Range)",
        "category": "swing",
        "one_liner": "A measure of how much a stock typically moves in a single day, in price terms.",
        "detail": (
            "ATR = 14-day average of max(High−Low, |High−PrevClose|, |Low−PrevClose|). "
            "A stock at ₹1,000 with ATR = ₹30 has typical daily swings of ₹30 (3%). "
            "ATR expands in volatile markets and contracts when the stock is quiet."
        ),
        "analogy": (
            "Think of ATR as the stock's 'heartbeat'. A calm stock has a small, steady heartbeat (low ATR). "
            "A volatile stock has a big, fast heartbeat (high ATR). "
            "Your stop loss should be placed far enough that the normal heartbeat doesn't knock you out. "
            "A sleeping patient's heartbeat varying by 5 bpm is fine. 50 bpm swings is unusual."
        ),
        "example": "ATR ₹30 on ₹1,000 stock = 3% daily range is normal. "
        "During earnings week, ATR might jump to ₹80 — that's why we avoid holding through earnings.",
        "how_to_use": (
            "Stop = entry − 1.5 × ATR. "
            "Position size = (1R in rupees) ÷ (1.5 × ATR). "
            "High ATR = more volatile = smaller position for same risk. "
            "Tranche spacing in accumulation is also ATR-based — subsequent buys are triggered when price "
            "drops by 1.5–5× ATR from previous buy."
        ),
    },
    {
        "name": "Expectancy R",
        "category": "swing",
        "one_liner": "Average R earned per trade across all closed trades. The most important performance metric.",
        "detail": (
            "Expectancy = (win rate × avg win in R) − (loss rate × avg loss in R). "
            "With 50% win rate, avg win 2R, avg loss 1R: expectancy = 0.5×2 − 0.5×1 = 0.5R per trade. "
            "Even a 40% win rate can be profitable if avg wins are 3R and avg losses are 1R."
        ),
        "analogy": (
            "Like a casino edge but in your favour. A casino wins 52% of coin flips and earns a small edge per flip. "
            "Run 10,000 flips and that edge compounds into significant profit. "
            "Expectancy 0.4R means every ₹1,000 risked on average returns ₹400 profit. "
            "Over 100 trades risking ₹5,000 each: ₹5,000 × 0.4 × 100 = ₹2,00,000 expected profit."
        ),
        "example": "40 closed trades: 20 wins avg +1.8R, 20 losses avg −1R. "
        "Expectancy = (0.5 × 1.8) − (0.5 × 1.0) = 0.90 − 0.50 = 0.40R.",
        "how_to_use": (
            "Expectancy > 0.3R = strategy is working well, maintain sizing. "
            "Expectancy 0.1–0.3R = marginal, review entry criteria or wait for more data. "
            "Expectancy < 0 = losing strategy. Reduce size to minimum or pause. "
            "Always check expectancy per bundle per regime separately — aggregate expectancy can mask a failing bundle."
        ),
    },
    {
        "name": "Pillar Breakdown (Swing Signal)",
        "category": "swing",
        "one_liner": "The breakdown of a signal's total score into 5 components: technical, expectancy, flow, regime fit, and fundamentals.",
        "detail": (
            "A swing signal with score 76 breaks down as: Technical 22 (chart quality), Expectancy 18 (historical win rate for this bundle/regime), "
            "Flow 12 (delivery % and smart money proxies), Regime Fit 14 (how well the setup fits current conditions), "
            "Fundamentals 10 (basic quality check)."
        ),
        "analogy": (
            "Like a judge scoring a gymnastics routine: separate marks for execution, difficulty, artistry, form, and landing. "
            "A high total could come from a flawless easy routine (all pillars decent) "
            "or a high-difficulty routine with one bad landing (Technical 28 but Flow 4)."
        ),
        "example": "Total 78: Technical 12, Expectancy 18, Flow 8, Regime Fit 15, Fundamentals 25. "
        "→ Great regime fit and fundamentals but weak chart setup and flow. Trade with caution on timing.",
        "how_to_use": (
            "Technical < 15/30: the chart setup isn't clean. Wait for a better entry or skip. "
            "Regime Fit < 10/15: conditions aren't ideal. Reduce size. "
            "Fundamentals < 8/15: the underlying business is mediocre. Higher failure risk on extended holds. "
            "All pillars balanced above their midpoints = cleanest trades."
        ),
    },
    # --- Market ---
    {
        "name": "Regime (BULL / BEAR / SIDEWAYS)",
        "category": "market",
        "one_liner": "The overall state of the Indian market — determines whether swing signals are actionable.",
        "detail": (
            "Calculated weekly from: % of Nifty 500 stocks above their 50-day and 200-day moving averages, "
            "advance/decline ratio, India VIX, and net FII/DII flow. "
            "Signals only execute in BULL. In SIDEWAYS/BEAR, all signals auto-downgrade to WATCH."
        ),
        "analogy": (
            "Like checking the weather before deciding what to wear. "
            "In BULL regime, the wind is at your back — most setups work better. "
            "In BEAR regime, even great setups are fighting a headwind — your win rate drops by ~15%. "
            "You can still trade in rain, but you'd wear a raincoat and go slower."
        ),
        "example": "Nifty at ATH with 65% of stocks above 50DMA, VIX at 12, FII buying → BULL. "
        "Nifty in correction with 38% above 50DMA, VIX at 21, FII selling → SIDEWAYS.",
        "how_to_use": (
            "BULL + breadth confirmed: full swing size, run all bundles. "
            "SIDEWAYS: reduce to 50% swing allocation, only VCP and Composite. "
            "BEAR: stop opening new swing positions. Let existing T1-hit positions ride. "
            "The regime is the single biggest driver of your win rate — never override it manually."
        ),
    },
    {
        "name": "India VIX",
        "category": "market",
        "one_liner": "India's 'fear index' — measures how much volatility the options market expects in Nifty over the next 30 days.",
        "detail": (
            "Derived from Nifty options prices. High VIX = big swings expected, lots of fear/uncertainty. "
            "Low VIX = market expects calm conditions (sometimes complacency). "
            "VIX > 20 signals fear; VIX < 13 signals calm."
        ),
        "analogy": (
            "Like a weather barometer — but for market storms. High pressure (VIX < 13) = clear skies. "
            "Falling pressure (VIX rising from 14 to 22) = storm incoming. "
            "Peak pressure (VIX at 30+) = the storm is here. "
            "Interestingly: VIX falling from a peak is often the best time to buy — the storm is passing."
        ),
        "example": "March 2020: VIX hit 86 — panic peak. Buying at VIX > 50 historically gives 30%+ returns over 12 months. "
        "Jan 2024: VIX at 11.5 (calm). Markets rallied further for months.",
        "how_to_use": (
            "VIX > 18: reduce new swing position sizes. "
            "VIX > 25: pause new positions entirely. "
            "VIX dropping from high levels (25 → 18 → 14): actually a buying signal — fear subsiding. "
            "Never panic sell at peak VIX — that's when everyone else is selling and the smart money is buying."
        ),
    },
    {
        "name": "Advance/Decline Ratio",
        "category": "market",
        "one_liner": "Stocks rising today ÷ stocks falling today. Measures breadth of market movement.",
        "detail": (
            "An A/D ratio of 2.5 means 2.5 stocks rose for every 1 that fell — strong broad-based rally. "
            "A/D of 0.5 means twice as many stocks fell as rose — broad weakness. "
            "Nifty can be flat but A/D tells you if the rally is narrow (big caps only) or broad."
        ),
        "analogy": (
            "Like counting how many players in a cricket team contributed. "
            "Even if the top 2 batsmen (Nifty heavyweights: Reliance, HDFC) are scoring, "
            "if 7 of 11 players are out for ducks, the team isn't really winning. "
            "A/D ratio tells you how many 'players' are contributing to the market's score."
        ),
        "example": "Nifty +0.8% but A/D = 0.7 (more stocks fell than rose) → narrow rally, leadership is thinning, be cautious. "
        "Nifty +1.2% with A/D = 3.2 → broad participation, healthy rally.",
        "how_to_use": (
            "Use as a confirmation tool. A/D consistently < 1 while Nifty is rising = deteriorating breadth, "
            "distribution happening underneath. Reduce new positions. "
            "A/D consistently > 2 for 4+ weeks = broad bull market, full allocation is justified. "
            "Breadth Confirmation requires A/D to cross a threshold alongside other regime indicators."
        ),
    },
    {
        "name": "FII / DII Flow",
        "category": "market",
        "one_liner": "Net buying (+) or selling (−) by foreign and domestic institutions on a given day.",
        "detail": (
            "FII = Foreign Institutional Investors (Goldman, BlackRock, etc.). "
            "DII = Domestic Institutional Investors (SBI MF, HDFC MF, LIC, etc.). "
            "Net flow = buys − sells in crores. Large positive = institutions deploying money. Large negative = withdrawing."
        ),
        "analogy": (
            "Like tracking the big players at a poker table. FII is the foreign high-roller — when they buy India, "
            "it's a macro confidence signal. DII is the local institution — they 'buy the dip' when FII sells. "
            "When both buy together: double confirmation. When both sell: serious concern."
        ),
        "example": "FII −₹5,000 Cr + DII +₹6,000 Cr: typical 'DII absorbs FII selling' pattern. Market holds up. "
        "FII +₹4,000 Cr + DII +₹3,000 Cr: both buying = strong bull impulse.",
        "how_to_use": (
            "3+ weeks of FII net selling: reduce swing exposure, especially in mid-caps. "
            "FII net buying resuming after a period of selling: consider this the start of the next leg. "
            "DII consistently buying: floor is being set, accumulation opportunities are better. "
            "Regime detection automatically incorporates this into the BULL/BEAR/SIDEWAYS label."
        ),
    },
    {
        "name": "Breadth Confirmation",
        "category": "market",
        "one_liner": "A BULL regime is 'breadth confirmed' when the rally isn't limited to just a few large-cap stocks.",
        "detail": (
            "Breadth confirmed = True when: % of stocks above 50DMA > threshold AND advance/decline ratio is healthy. "
            "Without breadth confirmation, BULL regime exists but the rally may be narrow and fragile. "
            "Accumulation-to-swing conversion (Bull Ready) requires breadth confirmed = True."
        ),
        "analogy": (
            "A football team where only 2 players are in top form while the other 9 are struggling. "
            "They might win one or two games, but the team isn't truly strong. "
            "Breadth confirmed means the whole team is playing well — a much more sustainable win."
        ),
        "example": "Nifty at all-time high with 68% of Nifty 500 above 50DMA → breadth confirmed. "
        "Nifty at all-time high with only 45% above 50DMA → narrow rally, breadth NOT confirmed.",
        "how_to_use": (
            "Breadth confirmed = True: highest conviction for both swing and accumulation positions. "
            "Breadth confirmed = False but BULL: proceed with swing positions but smaller size; "
            "don't convert accumulation positions to swing. "
            "A regime that flips from 'not confirmed' to 'confirmed' is a strong buy signal."
        ),
    },
    # --- Backtesting ---
    {
        "name": "IS / OOS (In-Sample / Out-of-Sample)",
        "category": "backtesting",
        "one_liner": "IS = data the strategy was built/tested on. OOS = data it has never seen. OOS results are what matter.",
        "detail": (
            "Any strategy tested on its own training data looks great — it's optimized for those conditions. "
            "OOS testing reveals whether the strategy actually works on new data, "
            "or whether it just memorized the past. Walk-forward splits data into rolling IS/OOS windows."
        ),
        "analogy": (
            "Exam preparation: IS = the practice question bank you studied. OOS = the actual exam. "
            "Anyone can score 95% on practice questions they've seen before. "
            "The real test is whether that knowledge generalizes to unseen questions. "
            "OOS Sharpe is your actual exam score."
        ),
        "example": "Trend bundle IS Sharpe = 1.8 (tested on 2020–2022 data used to build the bundle). "
        "OOS Sharpe = 1.1 (tested on 2023–2024, never seen before). "
        "OOS Sharpe 1.1 is the number to trust.",
        "how_to_use": (
            "Always focus on OOS Sharpe in the Walk-Forward results. "
            "IS Sharpe > OOS Sharpe by >50%: likely overfit — reduce live allocation. "
            "OOS Sharpe > 0.7 consistently across windows: robust strategy — maintain or increase. "
            "OOS Sharpe varying widely window-to-window: regime-dependent — trade only in matching regimes."
        ),
    },
    {
        "name": "Sharpe Ratio",
        "category": "backtesting",
        "one_liner": "Return per unit of risk. Mean(R per trade) ÷ Std(R per trade). Higher = more consistent profitability.",
        "detail": (
            "Sharpe = mean(realized_R) ÷ std(realized_R). "
            "A Sharpe of 1.0 means you earn exactly as much on average as your trades vary. "
            "Sharpe of 2.0 = returns are twice as large as volatility — extremely consistent. "
            "Sharpe of 0.3 = very bumpy ride for the profit earned."
        ),
        "analogy": (
            "Comparing two fund managers: "
            "Manager A earned 20% but went up 40% then down 25% then up 5% (bumpy). "
            "Manager B earned 15% in a smooth upward line. "
            "Manager B has a higher Sharpe. Same destination, much smoother journey. "
            "In trading, a smooth journey matters — drawdowns cause emotional decision-making."
        ),
        "example": "50 trades, mean R = 0.45, std R = 0.9 → Sharpe = 0.45/0.9 = 0.5 (decent). "
        "50 trades, mean R = 0.45, std R = 0.4 → Sharpe = 1.1 (excellent).",
        "how_to_use": (
            "Sharpe > 1.0: excellent — strategy is consistent and profitable. Size up. "
            "Sharpe 0.5–1.0: decent — keep trading at standard size, continue calibrating. "
            "Sharpe < 0.5: unstable — don't increase size. Review entry criteria. "
            "Compare IS vs OOS Sharpe in walk-forward to detect overfitting."
        ),
    },
    {
        "name": "Walk-Forward",
        "category": "backtesting",
        "one_liner": "A backtesting technique that tests a strategy on rolling out-of-sample windows to detect overfitting.",
        "detail": (
            "Splits all historical data into sliding windows: first 70% = IS (train/test), last 30% = OOS (simulate live). "
            "Repeat across many windows. Compares IS Sharpe vs OOS Sharpe per window. "
            "If OOS consistently matches IS: strategy is robust. If OOS drops sharply: strategy is overfit."
        ),
        "analogy": (
            "Driving lessons on different routes every week. If you can only drive Route A, "
            "you'll fail when the examiner takes you on Route B. "
            "Walk-forward = practicing on Routes A, B, C, D, E, F... and measuring how well you drive on each new route "
            "using only the skills learned from prior routes."
        ),
        "example": "8 walk-forward windows for 'Trend' bundle: "
        "IS Sharpe [1.8, 1.6, 2.0, 1.5, ...], OOS Sharpe [1.2, 1.1, 1.4, 1.0, ...]. "
        "Consistent OOS ≈ 70% of IS → robust strategy, no overfit flag.",
        "how_to_use": (
            "Run walk-forward before increasing allocation to any bundle. "
            "Check: is OOS Sharpe consistently ≥ 0.5? Are IS/OOS ratios consistent (not just one good window)? "
            "If overfit flag fires: gather 30 more live trades before sizing up. "
            "Walk-forward doesn't tell you the strategy WILL work — just that it HAS worked consistently out-of-sample."
        ),
    },
    {
        "name": "Overfit Flag",
        "category": "backtesting",
        "one_liner": "Warning that a strategy's backtest results may be 'too good to be true' — it memorised the past rather than learning from it.",
        "detail": (
            "Fires when OOS Sharpe drops > 50% vs IS Sharpe in at least 50% of walk-forward windows. "
            "E.g. IS Sharpe = 2.0, OOS Sharpe = 0.7 → drop = (2.0 − 0.7)/2.0 = 65% > 50% → counts as one overfit window."
        ),
        "analogy": (
            "A student who memorises every past exam paper. They score 95% on practice exams (IS). "
            "On the actual exam with new questions (OOS), they score 30%. "
            "The gap reveals memorisation, not understanding. The overfit flag catches this for trading strategies."
        ),
        "example": "8 windows: 5 windows where OOS drops > 50% of IS, 3 where it doesn't. "
        "5/8 = 62.5% > 50% → Overfit flag = YES.",
        "how_to_use": (
            "Overfit flag YES → don't scale up based on backtest. "
            "Gather 30+ live trades at minimum position size first. "
            "Review: did the bundle parameters get tuned to specific market conditions that no longer apply? "
            "Consider widening the regime filter or simplifying the bundle's entry criteria."
        ),
    },
    # --- Calibration ---
    {
        "name": "Calibration",
        "category": "calibration",
        "one_liner": "The system's live tracking of each bundle's real performance using your actual closed trades.",
        "detail": (
            "As you close trades, calibration updates win rate, expectancy, and confidence for each (bundle, regime) pair. "
            "Early on with few trades, confidence is low. After 30+ trades, estimates are reliable. "
            "The system uses this data to refine signal thresholds."
        ),
        "analogy": (
            "Like a weather model that gets better as it collects more real-world data. "
            "After 5 measurements: rough estimate, wide uncertainty. After 500: precise forecasts. "
            "Calibration is your trading model getting smarter with every trade you close."
        ),
        "example": "Trend bundle, BULL regime: 10 trades, win rate 60%, expectancy 0.4R → 'medium' confidence. "
        "After 40 trades: same numbers → 'high' confidence. Now you can trust and act on them.",
        "how_to_use": (
            "Check after every 10 closed trades. "
            "Low confidence (< 15 trades): don't change sizing based on these numbers. "
            "Medium (15–30): use conservatively. "
            "High (30+): reliable. If expectancy > 0.4R: consider slight size increase. If < 0.2R: review strategy."
        ),
    },
    {
        "name": "Wilson CI / Confidence Band",
        "category": "calibration",
        "one_liner": "The range of win rates consistent with your data. Wide band = little data. Narrow band = lots of data.",
        "detail": (
            "Wilson 95% confidence interval: with 10 trades and 6 wins (60% win rate), "
            "the true win rate could be anywhere from 31% to 83% — very wide. "
            "With 100 trades and 60 wins, the range narrows to 50%–69%. "
            "Confidence bands: Low (< 15 trades), Medium (15–30), High (30+)."
        ),
        "analogy": (
            "Election polling. 10 people polled: 6 say 'yes' (60%). But 10 people could easily be a fluke — "
            "the margin of error is enormous. 1,000 people polled: 600 say 'yes' — now you're confident it's ~60%. "
            "The confidence band is your polling margin of error."
        ),
        "example": "n=8: win rate 62.5%, CI [25%, 90%] — the true rate could be anywhere in that huge range. "
        "n=50: win rate 62%, CI [48%, 74%] — much more useful.",
        "how_to_use": (
            "Only make sizing decisions when confidence band is 'medium' or 'high'. "
            "Never increase size based on 5–8 trades — it's pure noise. "
            "When CI low end > 50%: even the pessimistic estimate suggests a winning strategy. "
            "When CI high end < 50%: even the optimistic estimate suggests a losing strategy — pause immediately."
        ),
    },
    # --- Signal & Position terms ---
    {
        "name": "MFE (Maximum Favourable Excursion)",
        "category": "swing",
        "one_liner": "The best unrealised gain a trade reached at any point before exit, in R units.",
        "detail": (
            "If you entered at ₹1,000 with stop ₹950 (1R = ₹50) and the stock touched ₹1,150 before you exited at ₹1,080, "
            "MFE = (₹1,150 − ₹1,000) ÷ ₹50 = +3.0R. Realized R was only +1.6R. "
            "The gap shows how much profit you 'gave back' before exiting."
        ),
        "analogy": (
            "Like the highest score you reached in a video game before losing your last life. "
            "MFE tells you the peak — even if you didn't 'cash out' at the peak. "
            "A consistent gap between MFE and realized R means your exit rules are leaving money on the table."
        ),
        "example": "Trade closed at +1.5R. MFE was +3.2R. → The stock hit T2 territory but you exited at T1. "
        "Pattern across many trades: consider holding T1-hit positions longer or trailing stop wider.",
        "how_to_use": (
            "MFE near realized R: you captured most of the available move. Good exit timing. "
            "MFE much higher than realized R: you exited too early. Review your trail-stop rules. "
            "Watch MFE distribution per bundle — Trend bundles should show higher MFE than Reversal."
        ),
    },
    {
        "name": "MAE (Maximum Adverse Excursion)",
        "category": "swing",
        "one_liner": "The deepest unrealised loss a trade reached at any point before exit, in R units.",
        "detail": (
            "If you entered at ₹1,000 with stop ₹950 and the stock briefly dipped to ₹965 before recovering and "
            "exiting at ₹1,080, MAE = (₹965 − ₹1,000) ÷ ₹50 = -0.7R. You almost hit the stop. "
            "MAE tells you how much heat the trade took."
        ),
        "analogy": (
            "Like the lowest your bank balance got during the month before payday. "
            "Even if you ended the month positive, MAE tells you how close you got to overdraft. "
            "Trades with high MAE that still win are stressful — and often a sign your entries are slightly too early."
        ),
        "example": "Trade closed at +2R, MAE was -0.8R. → Almost stopped out, then rallied. "
        "Distribution: if many winners have MAE worse than -0.5R, your entry timing is poor.",
        "how_to_use": (
            "MAE close to -1R consistently: entries are mistimed. Try entering on the next pullback. "
            "MAE very small (-0.2R or better) on most trades: entries are precise — stops could potentially be tighter. "
            "If a trade hits MAE -0.95R and recovers, don't celebrate — the rule is to honour the stop, not to hope."
        ),
    },
    {
        "name": "Trailing Stop",
        "category": "swing",
        "one_liner": "A stop loss that moves up as the price rises, locking in profits while letting winners run.",
        "detail": (
            "Once a trade hits T1, the stop is moved to entry price (risk-free position). "
            "As price climbs further, the stop trails behind at a defined distance (e.g. recent swing low, "
            "or N-bar low). When price reverses and hits the trailing stop, you exit with locked-in profit."
        ),
        "analogy": (
            "Like climbing a ladder and locking a safety harness one rung lower as you climb. "
            "If you slip, you only fall one rung — not all the way to the ground. "
            "The harness moves up with you, never down. You give up the absolute peak in exchange for guaranteed safety."
        ),
        "example": "Entry ₹1,000, T1 hit at ₹1,100. Stop moved to ₹1,000 (risk-free). "
        "Price rises to ₹1,180, trailing stop moves to ₹1,120. "
        "Price reverses to ₹1,118 → exit at +2.4R locked in.",
        "how_to_use": (
            "Never widen a trailing stop. Once it moves up, it doesn't come back down. "
            "Trail too tight = stopped out on normal noise. Trail too loose = give back too much. "
            "1.5–2× ATR below recent high is the standard. Different bundles have different trail rules — "
            "Trend bundle trails wider, Reversal bundle trails tighter."
        ),
    },
    {
        "name": "R:R (Risk-Reward Ratio, Drawn)",
        "category": "swing",
        "one_liner": "The ratio between potential profit (to T1) and potential loss (to stop) drawn at entry.",
        "detail": (
            "Drawn R:R = (T1 − Entry) ÷ (Entry − Stop). "
            "An entry at ₹100 with stop ₹95 (₹5 risk) and T1 at ₹115 (₹15 reward) has drawn R:R = 3.0×. "
            "This is the 'on paper' reward potential before any market action."
        ),
        "analogy": (
            "Like betting odds at a horse race. Drawn R:R = 3.0 means 'risk ₹100 to potentially win ₹300'. "
            "A bookie offering 3:1 on a horse isn't telling you the horse will win — just the payout if it does. "
            "Drawn R:R is the payout schedule; actual outcome depends on whether the trade works."
        ),
        "example": "Entry ₹500, stop ₹485 (risk ₹15), T1 ₹550 (reward ₹50) → drawn R:R = 3.33×. "
        "Entry ₹500, stop ₹485, T1 ₹515 → drawn R:R = 1.0× (poor setup).",
        "how_to_use": (
            "Drawn R:R ≥ 2.0× = good setup. The math works even at 40% win rate. "
            "Drawn R:R < 1.5× = marginal setup. Need >55% win rate to be profitable. "
            "When sorting signals, R:R is a useful filter — a setup with 3× R:R and a 60-point score "
            "is often better than a 75-point score with 1.2× R:R."
        ),
    },
    {
        "name": "Calibration n",
        "category": "signals",
        "one_liner": "The number of closed trades available to calibrate this bundle in this regime. More trades = more confidence.",
        "detail": (
            "Shown alongside every signal: 'n=84' means 84 closed trades exist for (this bundle, this regime). "
            "The confidence band is derived from n: <15 = low, 15–30 = medium, 30+ = high. "
            "Statistics computed on n < 15 are noise. n ≥ 30 is roughly when win rates stabilise."
        ),
        "analogy": (
            "Like Google Maps confidence. Walking directions based on 3 prior users' GPS tracks are unreliable — "
            "one detour skews the average. Directions based on 30,000 users are precise. "
            "Calibration n is the count of GPS tracks for your signal's specific bundle/regime combo."
        ),
        "example": "Signal n=8 → ignore the displayed win rate. It's noise. "
        "Signal n=84 → trust it. Use the displayed expectancy for sizing decisions.",
        "how_to_use": (
            "n < 15: treat the signal as exploratory. Use minimum size. "
            "n 15–30: standard size. Keep accumulating data. "
            "n > 30: full conviction. Size based on the displayed expectancy. "
            "If a bundle has been live for months and n is still < 15, it's a rare-setup bundle (like VCP) — that's normal."
        ),
    },
    {
        "name": "Signal Labels (BUY / BUY_WATCH / WATCH / HOLD / AVOID)",
        "category": "signals",
        "one_liner": "Per-signal classification telling you whether to act now, wait, or skip.",
        "detail": (
            "BUY: high score, conditions aligned, take the entry. "
            "BUY_WATCH: borderline score, watch for a cleaner entry trigger. "
            "WATCH: setup is forming but not ready. "
            "HOLD: existing position — don't add. "
            "AVOID: setup is broken or hard-avoid fired."
        ),
        "analogy": (
            "Like a traffic light specifically for that intersection. "
            "BUY = green, go. WATCH = flashing yellow, slow down and look. "
            "AVOID = red with a 'do not enter' sign. "
            "Other signals on the same screen might be green even if this one is red — each is independent."
        ),
        "example": "INFY trend bundle: score 78, label BUY → enter on next pullback. "
        "RELIANCE breakout bundle: score 62, label WATCH → wait for the next pipeline run.",
        "how_to_use": (
            "Only enter on BUY labels by default. BUY_WATCH = enter only with personal conviction at smaller size. "
            "WATCH/HOLD/AVOID = don't enter. "
            "In SIDEWAYS or BEAR regime, the system auto-downgrades many BUYs to WATCH — respect that."
        ),
    },
    {
        "name": "Trade States (OPEN / T1_HIT / CLOSED_WIN / CLOSED_LOSS / SCRATCHED / EXPIRED)",
        "category": "swing",
        "one_liner": "Lifecycle states of every swing trade from open to closed.",
        "detail": (
            "OPEN: just entered, neither stop nor target hit. "
            "T1_HIT: first target reached, half taken, stop moved to entry. "
            "CLOSED_WIN: exited at T1, T2, or trailing stop with positive R. "
            "CLOSED_LOSS: stopped out at original stop. "
            "SCRATCHED: exited near entry with ~0R. "
            "EXPIRED: closed after max hold period without resolving."
        ),
        "analogy": (
            "Like a movie ticket's lifecycle: bought (OPEN), entered theatre (T1_HIT), enjoyed it (CLOSED_WIN), "
            "walked out at intermission (SCRATCHED), or theatre closed early (EXPIRED). "
            "Each state tells you exactly where you are in the journey."
        ),
        "example": "Trade opens at ₹1,000 → state OPEN. Price hits T1 at ₹1,100 → state T1_HIT, stop moves to ₹1,000. "
        "Price climbs to ₹1,180 then drops to ₹1,000 → trailing stop hits → state CLOSED_WIN.",
        "how_to_use": (
            "OPEN positions still need active risk management — watch for the stop. "
            "T1_HIT positions are 'free shots' — let them ride to T2 unless thesis breaks. "
            "SCRATCHED trades are not losses — they're disciplined exits. "
            "EXPIRED trades suggest your max-hold setting may be too tight; review the timeframe."
        ),
    },
    {
        "name": "Position States (BUILDING / FULL / PAUSED / EXITED / CONVERTED_TO_SWING)",
        "category": "accumulation",
        "one_liner": "Lifecycle states of an accumulation position from tranche 1 to exit.",
        "detail": (
            "BUILDING: 1–4 tranches filled, more to come. "
            "FULL: all 5 tranches filled — full position established. "
            "PAUSED: thesis revalidation flagged a concern, but we haven't exited. New tranches blocked. "
            "EXITED: position closed (thesis broken or target met). "
            "CONVERTED_TO_SWING: in BULL regime, converted to a swing trade for shorter-horizon gains."
        ),
        "analogy": (
            "Like a construction project. BUILDING = foundation poured, walls going up. "
            "FULL = building complete, all floors occupied. "
            "PAUSED = construction halted (permit issue) but not demolished. "
            "EXITED = sold the building. CONVERTED_TO_SWING = rented it out for short-term gains instead of holding long-term."
        ),
        "example": "HDFCBANK: tranche 1 at ₹1,650 → BUILDING. Tranche 5 at ₹1,580 → FULL. "
        "Q4 EPS drops 40% → Hard Avoid fires → PAUSED. Thesis confirmed broken → EXITED.",
        "how_to_use": (
            "BUILDING is the normal active state — keep adding on triggers. "
            "FULL means you can stop watching for new entries and switch to monitoring. "
            "PAUSED is a yellow card — investigate the reason. Don't override blindly. "
            "EXITED positions still count for the postmortem — analyse why for future entries."
        ),
    },
    # --- Bundles (specific) ---
    {
        "name": "Trend Bundle",
        "category": "swing",
        "one_liner": "Buys stocks in established uptrends — higher highs and higher lows with momentum confirmation.",
        "detail": (
            "Looks for stocks with EMA stack (5 > 20 > 50 > 200), RSI in 45–70 (momentum but not extended), "
            "positive MACD histogram, and price within ~5% of 20-day high. "
            "Most reliable in BULL regime; downgraded to WATCH in SIDEWAYS."
        ),
        "analogy": (
            "Like jumping on a moving train. The train is already moving in the right direction — "
            "you're not predicting the start of the journey, just joining the ride. "
            "Risk: trains can derail or reverse, so you keep a tight stop near the platform."
        ),
        "example": "INFY: EMAs stacked correctly, RSI 58, MACD positive, near 20-day high → trend signal. "
        "Stop just below the 20-day low (out of normal noise but tight enough to limit loss).",
        "how_to_use": (
            "Trend is the bread-and-butter bundle — highest signal frequency. "
            "Win rate typically 50–55%, expectancy 0.4–0.6R in BULL. "
            "Avoid taking Trend signals in stocks that have already run 30%+ in the last month — they're extended."
        ),
    },
    {
        "name": "Breakout Bundle",
        "category": "swing",
        "one_liner": "Buys when price breaks above a multi-week resistance level on above-average volume.",
        "detail": (
            "Identifies a recent consolidation high (e.g. 20-day high) and triggers a buy when price closes above it "
            "with volume at least 1.5× the 20-day average. Stop just below the breakout level."
        ),
        "analogy": (
            "Like a dam breaking. Pressure builds for weeks (consolidation), then the dam gives way (breakout) "
            "and water rushes through. The volume surge is the evidence that the break is real, not a fake-out."
        ),
        "example": "TCS consolidates between ₹4,000–₹4,150 for 5 weeks. Closes at ₹4,170 on 2× volume → breakout. "
        "Stop at ₹4,090 (just inside the prior range).",
        "how_to_use": (
            "Breakouts that fail (fall back into the range) are common — that's why volume matters. "
            "Low-volume breakouts have ~40% failure rate; high-volume have ~25%. "
            "Always check the broader regime — breakouts work poorly in BEAR markets."
        ),
    },
    {
        "name": "Reversal Bundle",
        "category": "swing",
        "one_liner": "Buys oversold stocks showing reversal signs — like RSI bouncing from below 30 with bullish divergence.",
        "detail": (
            "Looks for RSI < 30, bullish divergence (price makes lower low but RSI makes higher low), "
            "candlestick reversal pattern (hammer, engulfing), and reclaim of a key support level. "
            "Lowest win rate of all bundles (~40%) but highest R:R when correct."
        ),
        "analogy": (
            "Like buying an umbrella at the end of monsoon — counter-intuitive but well-timed. "
            "Reversal trades catch falling knives. Most attempts fail, but successful ones reverse hard. "
            "You need disciplined stops because the strategy depends on infrequent big wins."
        ),
        "example": "Stock falls from ₹500 to ₹350. RSI hits 22. Next day price closes at ₹368 with a hammer candle → reversal signal. "
        "Stop at ₹345 (below the hammer low). T1 at ₹420 (R:R = 2.3×).",
        "how_to_use": (
            "Reversal needs the largest R:R cushion because of lower win rate. Don't take signals below 1.8× drawn R:R. "
            "Pair with quality fundamentals — reversals on broken businesses tend to keep falling. "
            "BULL regime reversal signals are high-probability; BEAR regime ones are essentially knife-catches."
        ),
    },
    {
        "name": "VCP (Volatility Contraction Pattern)",
        "category": "swing",
        "one_liner": "Identifies stocks tightly coiling with shrinking volatility before a high-probability breakout.",
        "detail": (
            "Looks for 3+ consecutive pullbacks of decreasing magnitude (e.g. -15%, -10%, -6%) with each base "
            "tightening. Volume contracts during pullbacks and expands on breakout. Made famous by Mark Minervini."
        ),
        "analogy": (
            "Like a coiled spring. Each successive bounce smaller than the last means energy is being stored, "
            "not released. When the spring finally lets go, the move is sharp and sustained. "
            "VCP catches stocks just before that release."
        ),
        "example": "Stock: ₹1,000 → drops to ₹850 (-15%) → recovers to ₹980 → drops to ₹880 (-10%) → recovers to ₹970 → "
        "drops to ₹915 (-6%). Each pullback is shallower. Breakout above ₹985 with volume = entry.",
        "how_to_use": (
            "Rarest bundle — maybe 2–4 signals per Sunday run on the full NSE 500. "
            "Highest expectancy when it triggers (often 0.7R+ in BULL). "
            "Don't anticipate the breakout — wait for the actual close above the contraction high."
        ),
    },
    {
        "name": "Composite Bundle",
        "category": "swing",
        "one_liner": "Requires 2+ other bundles (Trend, Breakout, Reversal, VCP) to agree before generating a signal.",
        "detail": (
            "When a stock simultaneously appears in Trend AND Breakout (or any 2+ combinations), Composite emits "
            "a high-conviction signal. The score is a weighted blend of the underlying bundles' scores. "
            "Lower frequency, higher quality."
        ),
        "analogy": (
            "Like a second medical opinion. One doctor's diagnosis (Trend) is good, but a second specialist (Breakout) "
            "confirming the same thing dramatically reduces error probability. "
            "Composite waits for that confirmation before acting."
        ),
        "example": "INFY shows Trend signal (score 70) AND Breakout signal (score 72) → Composite signal score 76. "
        "Higher than either alone; lower failure rate.",
        "how_to_use": (
            "Composite signals are the highest-conviction setups — full sizing is justified. "
            "Don't take Composite if you've already entered the underlying Trend or Breakout signal — same stock. "
            "Composite signals are rare in BEAR regime — patience required."
        ),
    },
    {
        "name": "PEAD (Post-Earnings Announcement Drift)",
        "category": "swing",
        "one_liner": "Buys stocks that surprise positively on earnings — capturing the multi-day drift after the announcement.",
        "detail": (
            "Looks for: earnings beat (actual EPS > estimate by >5%), positive forward guidance, gap up >2% on results day, "
            "and continuation in the next 1–3 sessions. Currently gated by spec C2 — paper-only until a full earnings season validates."
        ),
        "analogy": (
            "Like riding the wave of a viral product launch. The stock isn't 'pricing in' the surprise instantly — "
            "institutional buyers take days to position. You ride that drift."
        ),
        "example": "Company X reports EPS ₹15 (estimate ₹12, beat by 25%), raises guidance, gaps up 4%. "
        "Buy at next day's open; drift typically continues 5–10 days.",
        "how_to_use": (
            "Currently disabled in live sizing (spec C2 — paper-only). "
            "Don't manually override the gate. Once an earnings season's PEAD trades are net-positive with cost model on, "
            "the gate lifts. Until then, treat PEAD signals as research-only."
        ),
    },
    {
        "name": "SMC (Smart Money Concepts)",
        "category": "swing",
        "one_liner": "Identifies institutional accumulation/distribution patterns — order blocks, fair-value gaps, liquidity sweeps.",
        "detail": (
            "Hunts for: large-volume bars after consolidation (order blocks), price imbalances (fair-value gaps), "
            "stop-run reversals (liquidity sweeps). Currently gated by spec C3 — display-only, not in live seeding "
            "until pooled OOS evidence justifies it."
        ),
        "analogy": (
            "Like watching where the big fish swim in a pond rather than following ripples on the surface. "
            "SMC tries to read institutional footprints. Theoretically powerful but hard to validate "
            "with reliable data — hence the gating."
        ),
        "example": "Stock makes a sharp move down to sweep stops below a swing low, then reverses up strongly → "
        "liquidity sweep signal. Order block: a large bullish bar followed by 5+ bars of consolidation.",
        "how_to_use": (
            "Don't trade SMC signals live. Use them as a confirmation lens for other bundle signals. "
            "Watch the Strategy Lab to see how SMC performs in backtests. If pooled OOS Sharpe > 0.6 across regimes, "
            "the gate may lift in a future release."
        ),
    },
    # --- Signal pillars and chips ---
    {
        "name": "Technical Pillar",
        "category": "signals",
        "one_liner": "0–30 score for chart quality: trend, momentum, volume, support levels. The 'looks good on chart' score.",
        "detail": (
            "Combines EMA stack alignment, RSI position, MACD state, volume surge vs 20-day avg, and "
            "distance from recent breakout/support. Each bundle weights these differently."
        ),
        "analogy": (
            "Like a building inspector's score for structural integrity. Are the foundations (long-term trend) solid? "
            "Are the walls plumb (short-term momentum)? Is the roof leaking (recent rejection)? "
            "All combined into one number."
        ),
        "example": "Score 25/30: EMAs perfectly stacked, RSI 60, MACD positive crossover, 2× volume surge, near support. "
        "Score 12/30: EMAs mixed, RSI 45, weak volume → chart isn't supporting the thesis.",
        "how_to_use": (
            "Technical < 18 means the chart setup is mediocre. Even with high other pillars, the entry is risky. "
            "Look at the chart yourself when Technical is borderline. The number captures the rules — "
            "your eye catches what the rules miss."
        ),
    },
    {
        "name": "Expectancy Pillar",
        "category": "signals",
        "one_liner": "0–25 score for the historical expectancy of this bundle in the current regime — from calibration data.",
        "detail": (
            "Derived from Calibration table. If Trend bundle in BULL has historical expectancy 0.5R, "
            "this scores high. If the bundle has been losing recently (expectancy -0.1R), this scores low. "
            "Updates after every closed trade."
        ),
        "analogy": (
            "Like a player's career batting average. New signals get scored higher if the bundle has been "
            "performing well in recent history. The score reflects 'how often this exact setup has paid off lately'."
        ),
        "example": "Trend bundle: 84 trades, expectancy 0.45R → Expectancy pillar = 21/25. "
        "Same bundle, 8 trades, expectancy 0.05R → pillar = 4/25 (low n + low expectancy).",
        "how_to_use": (
            "Expectancy < 10 = bundle isn't producing in this regime. Skip the signal or size down. "
            "Expectancy 18–25 = bundle is on a hot streak. Standard or slightly larger size. "
            "Don't double-count — the pillar already encodes calibration, so don't manually check it too."
        ),
    },
    {
        "name": "Flow Pillar",
        "category": "signals",
        "one_liner": "0–15 score for institutional money flow signals — delivery %, ADV utilisation, FII direction.",
        "detail": (
            "Delivery % (shares delivered ÷ shares traded — high means buyers are holding, not flipping), "
            "ADV use % (today's volume vs 20-day average — surge implies institutional activity), "
            "FII net direction in the sector."
        ),
        "analogy": (
            "Like noticing who's at a restaurant. High Delivery % is a packed restaurant with people sitting down to eat. "
            "Low Delivery % is the same headcount but people grabbing takeout and leaving. "
            "Crowded with locals (institutional buyers) is a stronger signal than tourist traffic."
        ),
        "example": "Delivery 65%, ADV use 180%, FII net buyers → Flow = 13/15. "
        "Delivery 35%, ADV use 90%, FII selling → Flow = 4/15.",
        "how_to_use": (
            "Flow ≥ 10 = institutional confirmation. Bundle signals with strong Flow are highest conviction. "
            "Flow < 5 + a chart-only setup = often a retail-driven move. Tighter stops, smaller size. "
            "Flow data lags — it's reported end-of-day. Don't expect it to predict intraday."
        ),
    },
    {
        "name": "Sentiment Pillar",
        "category": "signals",
        "one_liner": "0–5 score for news/social sentiment — rare strong opinions count more than neutral noise.",
        "detail": (
            "Aggregates news sentiment (analyst upgrades/downgrades), insider activity (promoter buying), "
            "and social signal extremes. Capped at 5 because sentiment is notoriously noisy — it can't dominate the total."
        ),
        "analogy": (
            "Like crowd reaction at a sports game. Wildly cheering crowd (analyst upgrades, promoter buying) "
            "is a small but real signal. Quiet crowd (no news) tells you almost nothing. "
            "Sentiment doesn't decide the game — it adds context."
        ),
        "example": "3 broker upgrades in last 30 days + promoter bought ₹50 Cr → Sentiment = 4/5. "
        "No news, no insider activity → Sentiment = 1/5 (neutral).",
        "how_to_use": (
            "Sentiment 4–5 = a meaningful tailwind. Slight conviction boost. "
            "Sentiment ≤ 1 = neutral — don't weight it. "
            "Don't trade based purely on sentiment — it's intentionally capped because chasing news is a losing strategy."
        ),
    },
    {
        "name": "Regime Fit Pillar",
        "category": "signals",
        "one_liner": "0–15 score for how well the bundle's strategy fits the current market regime.",
        "detail": (
            "Trend and Breakout fit BULL strongly (high score). Reversal fits BEAR (range-bound). "
            "VCP can work in any regime but prefers BULL. In SIDEWAYS, most bundles score low — "
            "the system penalises trying to use trend strategies in choppy markets."
        ),
        "analogy": (
            "Like wearing the right outfit for the weather. Hiking boots (Trend bundle) are perfect for sunny weather (BULL). "
            "Wear them in heavy rain (BEAR) and you'll slip. Regime Fit measures whether your bundle is dressed appropriately."
        ),
        "example": "Trend bundle in BULL regime → Regime Fit = 14/15. "
        "Trend bundle in BEAR regime → Regime Fit = 3/15 (system tells you it's not the right strategy).",
        "how_to_use": (
            "Regime Fit < 8 is a major red flag — the bundle isn't suited to current conditions. "
            "If Regime Fit drops sharply between Sunday runs, the regime has likely shifted — review open positions. "
            "Composite signals require high Regime Fit on all underlying bundles."
        ),
    },
    {
        "name": "Fundamentals Pillar (Swing)",
        "category": "signals",
        "one_liner": "0–10 score for basic business quality — a fundamentals sanity check on swing entries.",
        "detail": (
            "Lightweight check: ROE > 12%, D/E < 1.5 for non-financials, no recent EPS collapse. "
            "Designed to filter out swing entries on broken businesses. Less rigorous than the accumulation pillars."
        ),
        "analogy": (
            "Like a health check before sprint training. A trader doesn't need full medical workup — "
            "just confirmation there's no acute illness. Even chart-based swing trades benefit from skipping companies in obvious decline."
        ),
        "example": "ROE 18%, D/E 0.4, EPS growing → Fundamentals = 9/10. "
        "ROE -5%, D/E 2.8, EPS collapsing → Fundamentals = 1/10 (the chart may look good but business is broken).",
        "how_to_use": (
            "Fundamentals < 5 + good Technical = possible 'dead cat bounce'. Trade smaller and tighter. "
            "Fundamentals 8–10 = even if held longer than intended, the underlying business won't catastrophically fail. "
            "Don't manually skip Fundamentals — let the score guide sizing."
        ),
    },
    {
        "name": "Delivery %",
        "category": "signals",
        "one_liner": "Percentage of traded shares that were taken delivery of (rather than intraday-flipped). High = institutional buying.",
        "detail": (
            "If 10 lakh shares traded today and 6 lakh were 'delivered' (transferred to buyer's demat), "
            "Delivery % = 60%. Intraday traders flip; institutions take delivery. High delivery % implies real buying interest."
        ),
        "analogy": (
            "Like counting how many concert-goers actually entered the venue vs how many bought tickets at the gate "
            "and resold them outside. The actual attendees are the people who care about the event."
        ),
        "example": "Delivery 70% on 2× volume surge → strong institutional accumulation. "
        "Delivery 30% on 2× volume → speculative day-trading; less meaningful.",
        "how_to_use": (
            "Delivery > 55% on volume surge = highest-quality entry signal. "
            "Delivery < 35% on volume surge = retail FOMO; expect a dip back. "
            "Track delivery % trend over 5–10 days — rising delivery during consolidation is bullish."
        ),
    },
    {
        "name": "ADV (Average Daily Volume) & ADV Use %",
        "category": "signals",
        "one_liner": "ADV = average daily volume over 20 days. ADV Use % = your position size as a fraction of that.",
        "detail": (
            "ADV is the trading liquidity benchmark for a stock. ADV Use % > 5% means your order is a meaningful "
            "fraction of daily turnover — you may move the price (slippage risk). Position sizing respects this."
        ),
        "analogy": (
            "Like trying to swim in a kiddie pool vs an ocean. Same swimming motion has different effects. "
            "A ₹1 lakh order in a high-ADV stock barely makes a ripple. The same order in a thin-volume stock "
            "shows up as a chart bar. ADV use % tells you which pool you're in."
        ),
        "example": "Stock ADV: 5 lakh shares. Your order: 2,500 shares → ADV use 0.5% (no impact). "
        "Stock ADV: 1 lakh shares. Same 2,500-share order → ADV use 2.5% (some slippage expected).",
        "how_to_use": (
            "ADV use < 1% = safe. ADV use 1–3% = expect 5–10 bps slippage. ADV use > 5% = expect significant slippage. "
            "Universe (PIT) filters out stocks below a min ADV — but always check personally on the day of entry. "
            "Reduce size or use limit orders in thin stocks."
        ),
    },
    {
        "name": "Circuit Hits (90d)",
        "category": "signals",
        "one_liner": "Count of upper/lower circuit triggers in the last 90 days. High count = volatile / manipulated stock.",
        "detail": (
            "An NSE 'circuit' is a price band (e.g. 5%, 10%, 20%) that, when hit, halts trading. "
            "Stocks with frequent circuit hits are usually low-float, low-quality, or subject to manipulation. "
            "The signal flag warns you when a stock has hit circuits ≥ 3 times in 90 days."
        ),
        "analogy": (
            "Like a sports car that keeps red-lining on a normal road. Maybe exciting, but the underlying behaviour "
            "is unreliable — it'll surprise you when you least expect it. Circuit-prone stocks are not for systematic trading."
        ),
        "example": "Microcap stock with 5 upper circuits + 3 lower circuits in 90 days → ⚠ chip shown. "
        "Large-cap like INFY: 0 circuit hits → no flag. Stable behaviour, suitable for systematic trades.",
        "how_to_use": (
            "Circuit hit warning visible → reduce position size by 50% minimum. "
            "More than 5 hits in 90 days → skip the trade. The stock's price action isn't reliable. "
            "Circuit-prone stocks often suffer surprise moves overnight — your stops may not protect you in a gap-open scenario."
        ),
    },
    {
        "name": "Earnings in Window",
        "category": "signals",
        "one_liner": "Warns when a quarterly result is expected within the trade's typical hold period.",
        "detail": (
            "Earnings cause 5–15% gap moves regardless of chart setup. The flag fires if announcement date "
            "falls within ~15 days of the typical trade hold. We avoid holding through earnings unless explicitly trading the event (PEAD)."
        ),
        "analogy": (
            "Like buying a house and finding out a major highway construction starts next week right outside. "
            "The 'normal' value of the property is suddenly meaningless. Earnings are highway construction for stocks — "
            "they reset the entire price discovery."
        ),
        "example": "Trade signal on Jan 20, earnings on Jan 30. Hold expected 10 days → ⚠ earnings in window. "
        "Trade signal on Feb 5, earnings already on Jan 30 → no flag (results released).",
        "how_to_use": (
            "Earnings warning = either skip, or close before announcement, or use 50% size. "
            "Don't 'hope to be out by then' — you'll likely overshoot. "
            "Mark earnings dates on your calendar; the dashboard relies on yfinance data which can lag by 1–2 days."
        ),
    },
    {
        "name": "Sector Heat",
        "category": "signals",
        "one_liner": "Aggregate R-exposure across all your trades in the same sector. Caps sector concentration.",
        "detail": (
            "If you have 3 open swing trades in IT (TCS, INFY, WIPRO) each risking 1R = 1%, sector heat = 3R = 3% of capital "
            "exposed to IT sector. Single-sector risk concentration. Most retail traders accidentally over-concentrate."
        ),
        "analogy": (
            "Like having multiple dishes at the same restaurant. If 3 of your 5 dinner orders are at one restaurant "
            "and it closes for inspection, half your dinner plans are gone. Sector heat tracks the same concentration risk."
        ),
        "example": "Open: Trade A in HDFC Bank (1R), Trade B in ICICI Bank (1R) → Banking sector heat = 2R. "
        "Triggers warning at sector heat > 3R.",
        "how_to_use": (
            "Sector heat > 3R = skip new signals in that sector even if score is high. "
            "Sector rotates suddenly; concentration risk amplifies losses. "
            "Use sector heat to diversify deliberately — pick the best signal in each underrepresented sector."
        ),
    },
    {
        "name": "Counterfactual",
        "category": "signals",
        "one_liner": "A short text explanation describing why the signal scored where it did — what would have to change for an upgrade.",
        "detail": (
            "Auto-generated for every signal: 'Would be BUY if Flow > 10. Currently Flow = 7 due to weak delivery %.' "
            "Tells you the specific blockers and what's missing. Helps you understand the system, not just trust it."
        ),
        "analogy": (
            "Like a teacher's grading rubric. You got 78 instead of 85 because of 'weak conclusion paragraph'. "
            "Now you know what to fix on the next test. Counterfactuals turn opaque scores into actionable feedback."
        ),
        "example": "'Score 71, would have been 78 (BUY) with delivery > 50%. Current delivery: 38% — "
        "watch for next 2–3 sessions; if delivery climbs above 50%, score will refresh on next pipeline run.'",
        "how_to_use": (
            "Read the counterfactual on every WATCH/BUY_WATCH signal — it tells you what to monitor. "
            "Don't act on a counterfactual prediction; wait for the next pipeline run to confirm. "
            "Useful for studying the system — over time you build intuition for what each pillar weight means."
        ),
    },
    {
        "name": "Dead Zone / Buy Zone (Score Chip)",
        "category": "signals",
        "one_liner": "Visual zone label classifying the signal's score — Dead Zone (skip), Watch Zone (monitor), Buy Zone (act).",
        "detail": (
            "Score < 50: Dead Zone (grey). Score 50–65: Watch Zone (yellow). Score 65–75: Buy Watch (amber). "
            "Score > 75: Buy Zone (green). Thresholds are configurable in Settings."
        ),
        "analogy": (
            "Like temperature zones for cooking. Cold (Dead Zone): nothing happens. Warming (Watch): "
            "monitor closely. Sizzling (Buy Zone): act now or burn the dish. "
            "The chip is colour-coded so you can scan dozens of signals at a glance."
        ),
        "example": "Signal score 47 → grey chip 'Dead Zone'. Signal score 78 → green chip 'BUY'. "
        "Many WATCH-zone signals become BUY in the next run as conditions evolve.",
        "how_to_use": (
            "Sort signals by zone. Focus on Buy Zone first — those are the actionable ones. "
            "Watch Zone signals deserve a quick chart check — sometimes you'll see what the system missed. "
            "Dead Zone = don't waste time. The score is too far from a signal."
        ),
    },
    {
        "name": "Elapsed to T1 %",
        "category": "swing",
        "one_liner": "What fraction of the typical hold-to-T1 time has elapsed for this trade. A pace tracker.",
        "detail": (
            "If trades in this bundle/regime typically hit T1 in 8 days and your trade has been open 4 days, "
            "Elapsed to T1 = 50%. If it's open 12 days and still no T1, Elapsed = 150% — the trade is overdue."
        ),
        "analogy": (
            "Like a flight tracker. Most flights of this distance take 8 hours. You're 4 hours in. "
            "If you're 14 hours in and not landed yet, something is wrong — fuel running low, weather delay, "
            "or wrong destination. Time itself is a signal."
        ),
        "example": "Bundle median time-to-T1: 7 days. Trade open 4 days → 57% elapsed (on track). "
        "Same trade at 14 days → 200% elapsed; usually a sign to exit even before stop hits.",
        "how_to_use": (
            "Elapsed > 150% on a trade still showing 0R: consider time-stop exit. "
            "Most bundles have a max hold (e.g. 21 days). After max hold, EXPIRED state auto-closes. "
            "Don't 'wait for the trade to work' — time is a cost. Capital tied up in a stale trade can't fund the next signal."
        ),
    },
    # --- Execution & cost model ---
    {
        "name": "Cost Model",
        "category": "execution",
        "one_liner": "Models real trading costs: brokerage, STT, exchange fees, GST. Applied to every backtest trade.",
        "detail": (
            "Round-trip cost for ₹1L worth of stock ≈ 0.15–0.25%. Over 100 trades a year, costs eat 15–25% of capital. "
            "Backtests with cost model disabled look artificially good. The cost model also factors in stamp duty and SEBI charges."
        ),
        "analogy": (
            "Like calculating your salary after tax. Gross salary (no cost model) looks great. "
            "Take-home (with cost model) is what you actually have. "
            "Strategies that look profitable without cost model often go negative with it."
        ),
        "example": "Trade: buy ₹1L worth, sell ₹1.02L worth. Gross profit ₹2,000. "
        "Cost ₹350 (brokerage + STT + GST). Net profit ₹1,650.",
        "how_to_use": (
            "Always backtest with cost model ON. The 'Cost model' toggle in Strategy Lab exists for diagnostic comparison only. "
            "If a bundle is barely profitable without cost model, it's losing money with it. "
            "Live trades automatically use real costs — the model matches your broker's actual charges."
        ),
    },
    {
        "name": "Fill Policy",
        "category": "execution",
        "one_liner": "Determines whether a signal at bar T can actually be filled at bar T+1 — enforces no-lookahead.",
        "detail": (
            "A signal on day T must execute at day T+1's open or later — never day T's close. "
            "If T+1's open gaps above the entry by > 0.5 ATR, the fill is skipped (slippage risk). "
            "If the stock's ADV is too low for your size, the fill is skipped. Prevents 'magic execution' in backtests."
        ),
        "analogy": (
            "Like the rule 'no Sunday trading'. Signals generated on Sunday can't be acted on until Monday open. "
            "Anyone backtesting with Sunday-execution is cheating. Fill policy enforces market hours and realistic execution."
        ),
        "example": "Signal generated EOD Monday. Tuesday open gaps up 2%. ATR is 1.5% → gap > 0.5 ATR → fill skipped (gap-too-far). "
        "If gap is < 0.5 ATR, trade fills at Tuesday's open + slippage.",
        "how_to_use": (
            "Always keep Fill Policy ON in Strategy Lab. The 'off' toggle is for diagnosis only. "
            "Live trades automatically respect fill policy — you can't enter a signal that didn't fill the rules. "
            "If your real-world execution differs much from the model, log a Real Fill so calibration can adjust."
        ),
    },
    {
        "name": "Slippage (bps)",
        "category": "execution",
        "one_liner": "The difference between expected fill price and actual fill price, in basis points. 100 bps = 1%.",
        "detail": (
            "Caused by market impact (your order moves the price) and bid-ask spread. "
            "Modeled per ATR and ADV use %: liquid stocks at small size = 2–5 bps. Thin stocks at large size = 20–50 bps. "
            "Tracked on every fill for postmortem analysis."
        ),
        "analogy": (
            "Like the difference between a restaurant's online menu price and the final bill (with taxes and tip). "
            "Small in low-traffic restaurants, large in popular ones. "
            "Add up over 100 visits and it's significant."
        ),
        "example": "Expected entry ₹100.00, actual fill ₹100.08 → slippage = 8 bps. "
        "On 100 trades, 8 bps × 2 (round-trip) = 16 bps × 100 = 16% of capital eaten by slippage alone if uncontrolled.",
        "how_to_use": (
            "Use limit orders for ADV use > 1%. Use market orders only in deep liquidity. "
            "If your post-mortem shows slippage_delta_bps consistently > 10, your execution needs improvement — "
            "either trade more liquid stocks or use limit orders."
        ),
    },
    {
        "name": "Mock vs Real Fill",
        "category": "execution",
        "one_liner": "Mock = simulated fill by the backtest/paper trading. Real = the actual fill logged from your broker.",
        "detail": (
            "Mock fills are used to simulate paper trades and backtest. Real fills are entered after you place an actual broker order. "
            "Tracking both lets the system measure execution drift — how much your live results differ from the model."
        ),
        "analogy": (
            "Like a recipe's expected cooking time vs your kitchen's actual cooking time. "
            "Mock = the cookbook. Real = your kitchen. Compare both to learn whether your stove (broker) is hotter or cooler than standard."
        ),
        "example": "Mock fill: BUY 100 shares at ₹500.00 (model price). "
        "Real fill from broker: BUY 100 shares at ₹500.45. Slippage delta = 9 bps, tracked.",
        "how_to_use": (
            "Always log Real Fills via the 'Log entry fill' button on signals. "
            "Real fills create the actual trade record. Mocks only exist in backtest. "
            "Postmortem compares real vs mock to detect execution-quality drift."
        ),
    },
    {
        "name": "Lookahead Violation",
        "category": "backtesting",
        "one_liner": "An attempted backtest fill that uses information not available at signal time — counts as a bug.",
        "detail": (
            "If a signal on day T tries to fill at day T's open (impossible — open already happened), the runner flags a lookahead violation. "
            "The trade isn't executed. The count is shown in backtest results — non-zero means a bug in bundle code."
        ),
        "analogy": (
            "Like a sports better placing bets after the game ends. Obviously cheating. "
            "Lookahead violations are subtle bugs that make backtests look magical — the system blocks and counts them."
        ),
        "example": "Backtest output: '0 lookahead violations' = clean. "
        "'8 violations' = bundle has a bug; fix before trusting the results.",
        "how_to_use": (
            "Always check lookahead_violations is 0 in the Strategy Lab output. "
            "Non-zero = file a bug report. Don't trust the win rate or expectancy until fixed. "
            "This is your safety net against accidentally writing a clairvoyant bundle."
        ),
    },
    # --- Risk & capital ---
    {
        "name": "Cash Decision (Deploy Count)",
        "category": "market",
        "one_liner": "How many swing positions to deploy and how much cash to hold back, given the current regime and signal supply.",
        "detail": (
            "If 4 BUY signals exist but the system says deploy_count = 2 (cash_pct_of_pool = 50%), "
            "you take the 2 best signals and hold 50% of swing capital in cash. "
            "Forced cash holding during weak regimes prevents over-deployment."
        ),
        "analogy": (
            "Like a fund manager's decision: 'Even if 10 great stocks appear, only deploy 50% if the macro is uncertain.' "
            "Discipline beats greed. Cash is a position — and sometimes the best one."
        ),
        "example": "BULL + breadth confirmed + 6 signals → deploy 6, cash 0%. "
        "SIDEWAYS + 6 signals → deploy 3, cash 50%. "
        "BEAR + 6 signals → deploy 0, cash 100%.",
        "how_to_use": (
            "Always respect the cash decision. Don't 'force' more deployments. "
            "Cash sitting in the pool isn't lost — it's preserved for the next BULL regime. "
            "If you consistently override the cash decision, your drawdowns will be 2–3× larger."
        ),
    },
    {
        "name": "Drawdown Governor",
        "category": "market",
        "one_liner": "Automatically reduces position size after a portfolio drawdown — requires 3 days of recovery to fully restore.",
        "detail": (
            "If portfolio value drops 5% from high-water mark, size multiplier drops to 0.5×. "
            "After 3 consecutive days of recovery (each day's NAV > previous day), multiplier restores to 1.0×. "
            "Prevents the 'revenge trading' spiral after losses."
        ),
        "analogy": (
            "Like a circuit breaker in your house. Power surge (drawdown) trips the breaker (reduce size). "
            "You don't just flip it back immediately — you investigate first (3-day recovery period). "
            "Once stable, full power resumes."
        ),
        "example": "Portfolio peak ₹10L. Drops to ₹9.2L (-8%). Size multiplier drops to 0.5×. "
        "Recovers to ₹9.4L, then ₹9.5L, then ₹9.7L (3 consecutive up days) → multiplier back to 1.0×.",
        "how_to_use": (
            "Don't override the governor. The math says smaller size after drawdowns improves recovery. "
            "If your drawdown is from a specific bundle failing (not the regime), pause that bundle manually. "
            "The governor doesn't know — it sees portfolio-level drawdown only."
        ),
    },
    {
        "name": "High Water Mark",
        "category": "market",
        "one_liner": "The highest portfolio value ever reached. Used as the reference point for drawdown calculations.",
        "detail": (
            "HWM updates on every NAV peak. Drawdown % = (current NAV − HWM) ÷ HWM. "
            "HWM never decreases — only the drawdown % changes when NAV moves. Critical for performance accounting."
        ),
        "analogy": (
            "Like the highest score you ever achieved in a game. Future scores get measured against it. "
            "Until you beat it, you're in 'drawdown'. Beating it means making a new HWM."
        ),
        "example": "Portfolio: ₹10L → ₹11L (new HWM ₹11L) → ₹10.5L (drawdown -4.5% from HWM) → ₹11.2L (new HWM ₹11.2L). "
        "HWM only ratchets up.",
        "how_to_use": (
            "Watch the gap between current NAV and HWM — that's your drawdown. "
            "When drawdown reaches certain thresholds, the Drawdown Governor activates. "
            "Long periods stuck below HWM = strategy may need rest or recalibration."
        ),
    },
    # --- Pipeline / scheduler ---
    {
        "name": "Sunday Run / Monday Revalidation / Midweek Mini",
        "category": "execution",
        "one_liner": "The three pipeline schedules: full Sunday refresh, Monday open re-check, and optional midweek mini-screen.",
        "detail": (
            "Sunday Run: full screen of NSE 500 across all bundles + accumulation candidates. The main pipeline. "
            "Monday Revalidation: re-checks Sunday signals against Monday's pre-market data — drops signals that no longer fit. "
            "Midweek Mini: lighter screen on Wednesday/Thursday for fresh setups. Off by default."
        ),
        "analogy": (
            "Like meal prep. Sunday: cook the week's main meals (full screen). "
            "Monday: check what's fresh and what spoiled overnight (revalidation). "
            "Midweek: a quick snack if you need it (mini screen). "
            "The big work happens once a week; the rest is upkeep."
        ),
        "example": "Sunday Run finds 8 BUY signals. Monday Revalidation drops 2 (gap-up made entry too expensive). "
        "User trades the remaining 6 throughout the week.",
        "how_to_use": (
            "Trigger Sunday Run after market close Friday or any time Saturday/Sunday. "
            "Always wait for Monday Revalidation before placing orders — it filters stale signals. "
            "Enable Midweek Mini only if you have time to actively trade midweek; otherwise the 2-stage flow is enough."
        ),
    },
    {
        "name": "Run ID",
        "category": "execution",
        "one_liner": "Unique identifier for each pipeline execution — every signal and candidate is tagged with the run that produced it.",
        "detail": (
            "Format: ULID (sortable, timestamp-prefixed). Lets you query: 'show me all signals from this Sunday's run' "
            "or 'compare last week's run to this week's'. Stored in run_log table with start/end timestamps."
        ),
        "analogy": (
            "Like the batch number on a packaged food. Every batch has a unique ID so you can trace any product "
            "back to its specific production run. Useful when something goes wrong — you know which batch to recall."
        ),
        "example": "Sunday Run triggered → returns run_id '01HXYZ123ABCDEF'. "
        "All signals from that run share this ID; query the DB by run_id for the full batch.",
        "how_to_use": (
            "Mostly invisible during normal use. "
            "Useful for debugging: 'why did this signal appear?' — look up the run_id's details_json. "
            "Postmortems group performance by run_id."
        ),
    },
    {
        "name": "Auto-Tune / Tuner Proposals",
        "category": "calibration",
        "one_liner": "The system's recommendation engine for adjusting bundle thresholds based on live performance.",
        "detail": (
            "After enough closed trades, the tuner suggests: 'Trend bundle score threshold could move from 70 → 72 — "
            "increases win rate by 4% with minimal signal loss.' "
            "If auto-tune is ON, the system applies the change. If OFF, you manually approve in the Calibration window."
        ),
        "analogy": (
            "Like a thermostat that learns. After 2 weeks, it suggests 'I notice you turn the AC down to 22 most evenings — "
            "should I do that automatically?'. You can say yes (auto-tune ON) or keep approving manually."
        ),
        "example": "Proposal: 'Trend signal threshold 70 → 72. Estimated impact: -8% signal count, +6% win rate, +0.15R expectancy.' "
        "Click 'Apply' to enact.",
        "how_to_use": (
            "Keep auto-tune OFF initially — review proposals manually to learn the system. "
            "After ~3 months of stable performance, enable auto-tune for hands-off improvement. "
            "Reject proposals that move thresholds dramatically — gradual changes are safer."
        ),
    },
    # --- Reports ---
    {
        "name": "Postmortem (Weekly)",
        "category": "calibration",
        "one_liner": "Weekly report showing closed trades, benchmark comparison, and per-bundle pull-through.",
        "detail": (
            "Generated every Sunday for the prior week. Shows: realized P&L in R units, win rate, "
            "benchmark comparison (Plutus vs Nifty vs regime-switched buy-hold vs random-liquid), "
            "and where each bundle's signals ended up. Stored as markdown reports."
        ),
        "analogy": (
            "Like a coach's match review. After every game, watch the tape: what worked, what didn't, "
            "which players (bundles) performed, which need bench time. Postmortems institutionalise that review."
        ),
        "example": "Week ending 2026-01-12: +2.1R realized, 6 closed trades (4 wins, 2 losses). "
        "Trend bundle: 3 trades, +1.8R. Reversal: 3 trades, +0.3R. Nifty: +1.1% same week.",
        "how_to_use": (
            "Read every postmortem. If Plutus underperforms benchmarks 3+ weeks in a row, investigate. "
            "Compare bundle pull-through — consistently weak bundles deserve threshold tightening. "
            "Don't react to single-week variance. The postmortem is the source of truth for weekly performance."
        ),
    },
    {
        "name": "Benchmarks (Plutus vs Nifty vs Regime-Switched vs Random Liquid)",
        "category": "calibration",
        "one_liner": "Four comparison baselines that contextualise your weekly performance.",
        "detail": (
            "Plutus net %: your strategy's actual return after costs. "
            "Nifty net %: buy-hold Nifty 50 over the same period. "
            "Regime-switched net %: simple BUY in BULL / CASH in BEAR strategy. "
            "Random liquid: random picks from the universe. "
            "Beating ALL four is the goal; beating Nifty alone isn't enough."
        ),
        "analogy": (
            "Like grading on multiple curves: vs class average (Nifty), vs honor roll (regime-switched), "
            "vs lottery (random). You want to beat all three to know your edge is real, not lucky."
        ),
        "example": "Week: Plutus +3.2%, Nifty +1.1%, Regime-switched +0.8%, Random liquid -0.4%. "
        "Plutus beat all 3 → genuine edge that week.",
        "how_to_use": (
            "Plutus must beat all 4 benchmarks averaged over rolling 8 weeks for the go-live bar. "
            "Beating only Nifty isn't enough — random luck does that ~50% of the time. "
            "Underperforming regime-switched means a simple binary regime model would do better — review your bundles."
        ),
    },
    {
        "name": "Profit Factor",
        "category": "calibration",
        "one_liner": "Sum of all winning trades ÷ sum of all losing trades, in R. > 1 = profitable. > 2 = strong.",
        "detail": (
            "Profit Factor = total R won ÷ |total R lost|. "
            "10 trades: 5 wins of +2R each (=10R), 5 losses of -1R each (=5R). PF = 10/5 = 2.0. "
            "PF > 1.5 is the rough benchmark for a sustainable strategy."
        ),
        "analogy": (
            "Like a casino's house edge expressed as a ratio. For every ₹1 paid out in winnings, the casino takes ₹2 in losses. "
            "Profit Factor 2.0 means your winners are paying for losers twice over."
        ),
        "example": "30 closed trades. Wins total +25R, losses total -10R. PF = 2.5 (excellent). "
        "Same 30 trades, wins +12R, losses -15R. PF = 0.8 (losing strategy).",
        "how_to_use": (
            "PF > 2.0: strong strategy, maintain size. "
            "PF 1.2–2.0: marginal, watch closely. "
            "PF < 1.0: losing strategy, pause and review. "
            "Always compute per-bundle profit factor — aggregate PF can mask a failing component."
        ),
    },
    {
        "name": "Bull-Ready (Convert to Swing)",
        "category": "accumulation",
        "one_liner": "An accumulation position that's broken into BULL regime is offered as a candidate to convert into a swing trade.",
        "detail": (
            "When regime flips BULL + breadth confirmed + the underlying stock shows a swing setup, the system "
            "highlights the accumulation position as 'Bull-Ready'. You can convert it (changes state to CONVERTED_TO_SWING). "
            "Voluntary — never auto-converted."
        ),
        "analogy": (
            "Like upgrading a long-term savings account to a fixed deposit when interest rates rise. "
            "Same money, but the new vehicle is better suited to current conditions. "
            "The decision is yours; the system flags the opportunity."
        ),
        "example": "Position in HDFCBANK accumulated at avg ₹1,580 over 5 tranches. "
        "Regime flips BULL, breakout signal appears at ₹1,720 → Bull-Ready badge shown. "
        "Convert: now a swing trade with stop at ₹1,650, T1 ₹1,800.",
        "how_to_use": (
            "Convert only if you intend to manage it as a swing (active stop, target). "
            "Don't convert just because the badge appears — the trade-off is that you cap upside at T2. "
            "If you believe the multi-year thesis is still intact, keep it as accumulation."
        ),
    },
    {
        "name": "PIT Universe (Point-in-Time)",
        "category": "execution",
        "one_liner": "The list of tradeable stocks as of a specific past date — no survivorship bias.",
        "detail": (
            "Backtests use the universe that existed on each historical date, not today's universe. "
            "Prevents 'cheating' by retroactively only including stocks that survived. "
            "Filter: median traded value > threshold (liquidity) and in NSE 500 on that date."
        ),
        "analogy": (
            "Like rebuilding the recipe of a 1990 cake using only ingredients available in 1990. "
            "If you secretly add 2020 ingredients (today's universe), the recipe isn't authentic. "
            "PIT universe enforces authenticity in backtests."
        ),
        "example": "Backtesting 2020 → universe = NSE 500 constituents as of 2020 + their liquidity then. "
        "Includes Yes Bank (was in index then). Excludes Adani Green (joined later).",
        "how_to_use": (
            "PIT is automatic — you don't configure it. "
            "If a backtest looks too good to be true, ask: 'is this using PIT?'. "
            "Without PIT, returns can be inflated by 3–8% per year just from survivorship bias."
        ),
    },
    {
        "name": "Promoter Pledge",
        "category": "accumulation",
        "one_liner": "Percentage of promoter (founder/major shareholder) shares pledged as loan collateral. Sudden rises are dangerous.",
        "detail": (
            "If a promoter pledges 30% of their shares for personal loans and the stock falls, "
            "the lender forces a margin sale that crashes the stock further. "
            "Hard Avoid triggers on jumps > 10 percentage points within a year."
        ),
        "analogy": (
            "Like a CEO using their company shares as collateral for a personal yacht loan. "
            "If the stock falls, the bank seizes their shares and dumps them on the market. "
            "Knowing this is happening before you accumulate is critical."
        ),
        "example": "Promoter pledge was 5% last year, now 22% → +17 pp jump → Hard Avoid fires. "
        "Even if business looks healthy, the structural risk is now elevated.",
        "how_to_use": (
            "Hard Avoid covers this automatically. Don't override unless you have specific knowledge. "
            "High pledge (>30%) historically correlates with corporate governance issues — "
            "sometimes legitimate (M&A funding), often the start of trouble."
        ),
    },
    {
        "name": "Going Concern",
        "category": "accumulation",
        "one_liner": "Auditor's red flag that the company may not survive the next 12 months. Auto-disqualifies from accumulation.",
        "detail": (
            "Issued in the audit report when liquidity is severely strained. "
            "Often precedes bankruptcy by 6–18 months. Statistically, ~30% of going-concern firms eventually file for bankruptcy."
        ),
        "analogy": (
            "Like a doctor noting 'patient at risk of mortality within a year' on a health record. "
            "Many patients survive. But you wouldn't pick that one as your long-term running partner. "
            "Going concern is the same warning for businesses."
        ),
        "example": "Mid-cap pharma's annual report contains a going-concern note from auditor. "
        "Hard Avoid fires regardless of how undervalued the stock looks.",
        "how_to_use": (
            "Always respect the going-concern flag. Most retail traders ignore this and get burned. "
            "If the company resolves the concern (raises capital, restructures), the flag clears in subsequent audits. "
            "Until then, accumulate elsewhere."
        ),
    },
    {
        "name": "F&O (Futures & Options) Listed",
        "category": "execution",
        "one_liner": "Whether the stock has derivatives listed on it. F&O stocks have deeper liquidity and tighter spreads.",
        "detail": (
            "F&O-listed stocks (~190 names on NSE) trade in larger volumes and have continuous price discovery. "
            "Non-F&O stocks can be illiquid and prone to circuit hits. "
            "Some bundles (e.g. Reversal) prefer F&O stocks for execution quality."
        ),
        "analogy": (
            "Like comparing highway driving (F&O — wide lanes, fast traffic) to country roads (non-F&O — bumpy, unpredictable). "
            "Same destination, very different experience."
        ),
        "example": "RELIANCE: F&O listed, daily volume ₹2,500 Cr → tight execution. "
        "Smallcap XYZ: non-F&O, daily volume ₹15 Cr → wider spreads, more slippage.",
        "how_to_use": (
            "Filter to F&O when execution quality matters most (Reversal bundle, larger position sizes). "
            "Accumulation can include non-F&O — long horizons absorb execution differences. "
            "Universe filter automatically removes the thinnest stocks; F&O is a stricter subset."
        ),
    },
    {
        "name": "ATH (All-Time High)",
        "category": "market",
        "one_liner": "The highest price the stock has ever traded at. Stocks at ATH are momentum, not 'expensive'.",
        "detail": (
            "A common retail mistake: avoiding ATH stocks because they 'feel expensive'. "
            "Empirically, stocks at ATH continue higher more often than they reverse. "
            "Momentum strategies (Trend, Breakout) intentionally target near-ATH stocks."
        ),
        "analogy": (
            "Like avoiding a marathon's leader because 'they've run the most kilometres'. "
            "The leader is usually the leader for a reason — they're the strongest. "
            "Same with stocks — being at ATH is evidence of strength, not a warning sign."
        ),
        "example": "GRINDWELL near ATH with positive momentum, RSI 58, MACD strong → valid Trend signal. "
        "Just because price is high doesn't mean it's overpriced.",
        "how_to_use": (
            "Don't manually skip signals because the stock is 'near ATH'. "
            "Trust the bundle logic — extension checks happen via RSI and ATR bands. "
            "If you don't trust ATH momentum strategies, switch to Reversal or VCP bundles."
        ),
    },
    {
        "name": "Score (Total)",
        "category": "signals",
        "one_liner": "The sum of all pillar scores for a signal, out of 100. Higher = stronger conviction.",
        "detail": (
            "Swing signal score = Technical + Expectancy + Flow + Sentiment + Regime Fit + Fundamentals. "
            "Accumulation candidate score = Quality + Growth + Valuation + RS Blend. "
            "Both scales are 0–100 for direct comparison."
        ),
        "analogy": (
            "Like an exam total: aggregate of subject marks. "
            "Some students score 80 by being excellent in 2 subjects. Others by being balanced 70 across the board. "
            "The total tells you overall quality; the pillar breakdown tells you the shape."
        ),
        "example": "Signal: Technical 24 + Expectancy 18 + Flow 12 + Sentiment 3 + Regime Fit 13 + Fundamentals 8 = 78. "
        "Above dead-zone threshold (65) → BUY label.",
        "how_to_use": (
            "Score above the buy-zone threshold = act. "
            "Two signals with same score can have very different pillar shapes — always check the breakdown. "
            "A 78 with balanced pillars beats a 78 with one pillar carrying the rest."
        ),
    },
    {
        "name": "SPRT (Sequential Probability Ratio Test)",
        "category": "calibration",
        "one_liner": "A running statistical test that decides whether a bundle has proven itself (or failed) — no fixed sample size needed.",
        "detail": (
            "SPRT compares two hypotheses: H0 = strategy has win rate 40% (doesn't work), H1 = win rate 60% (works). "
            "After every closed trade, it updates. When evidence accumulates enough: 'accept_H1' (proven), "
            "'accept_H0' (disproven), or 'continue' (need more data)."
        ),
        "analogy": (
            "A quality control inspector who doesn't wait for the full batch to be produced. "
            "After each item, they test it and update their judgment. "
            "After enough bad items: scrap the batch early. After enough good ones: approve early. "
            "SPRT is more efficient than waiting for a predetermined sample size."
        ),
        "example": "Start: 'continue'. After 12 trades (9 wins): 'continue'. After 25 trades (18 wins): 'accept_H1'. "
        "Strategy is statistically proven. After 30 trades (10 wins, win rate dropping): 'accept_H0'. Pause strategy.",
        "how_to_use": (
            "accept_H1: strong evidence the strategy works at its target win rate. Maintain or increase allocation. "
            "continue: gathering evidence. Stay at standard size. Don't change anything. "
            "accept_H0: strong evidence the strategy isn't meeting the target win rate. Review and reduce size. "
            "SPRT is automatic — the system updates it every Sunday pipeline run."
        ),
    },
]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_CATEGORY_COLORS: dict[str, str] = {
    "accumulation": "#7c3aed",
    "swing": "#d97706",
    "market": "#0284c7",
    "backtesting": "#059669",
    "calibration": "#dc2626",
    "signals": "#e11d48",
    "execution": "#0891b2",
}

_CATEGORY_LABELS = {
    "accumulation": "Accumulation",
    "swing": "Swing",
    "market": "Market",
    "backtesting": "Backtesting",
    "calibration": "Calibration",
    "signals": "Signals",
    "execution": "Execution",
}


def _badge(category: str) -> str:
    color = _CATEGORY_COLORS.get(category, TEXT_SECONDARY)
    label = _CATEGORY_LABELS.get(category, category)
    return (
        f'<span style="background:{color}22; color:{color}; font-size:10px; '
        f"font-weight:600; padding:2px 7px; border-radius:10px; "
        f'letter-spacing:0.03em; text-transform:uppercase;">{label}</span>'
    )


def _matches(term: dict, query: str) -> bool:
    if not query:
        return True
    q = query.lower()
    return any(
        q in str(v).lower()
        for v in [
            term["name"],
            term["category"],
            term["one_liner"],
            term["detail"],
            term["analogy"],
            term.get("example", ""),
            term["how_to_use"],
        ]
    )


def render(data: object = None) -> None:  # noqa: ARG001
    st.title("Glossary")
    st.caption(f"{len(_TERMS)} terms — search to filter, click to expand")

    query = st.text_input(
        "Search",
        placeholder="e.g.  rs blend  ·  sharpe  ·  tranche  ·  hard avoid",
        key="glossary_search",
        label_visibility="collapsed",
    )

    # Category filter
    all_cats = ["All"] + list(_CATEGORY_LABELS.values())
    cat_filter = st.selectbox(
        "Category", all_cats, key="glossary_cat", label_visibility="collapsed"
    )
    cat_key = {v: k for k, v in _CATEGORY_LABELS.items()}.get(cat_filter)

    filtered = [
        t
        for t in _TERMS
        if _matches(t, query.strip()) and (cat_key is None or t["category"] == cat_key)
    ]

    if not filtered:
        st.info("No terms match your search. Try a shorter keyword.")
        return

    st.caption(f"{len(filtered)} term{'s' if len(filtered) != 1 else ''} found")

    for term in filtered:
        expanded = bool(query.strip())  # auto-expand when searching
        with st.expander(
            f"{term['name']}",
            expanded=expanded,
        ):
            st.markdown(_badge(term["category"]), unsafe_allow_html=True)
            st.markdown(
                f'<div style="font-size:14px; color:{TEXT_PRIMARY}; margin:10px 0 4px;">'
                f"{term['one_liner']}</div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                f'<div style="background:{SURFACE}; border-radius:6px; padding:10px 14px; margin-bottom:6px;">'
                f'<div style="font-size:11px; font-weight:600; color:{TEXT_TERTIARY}; '
                f'text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;">Detail</div>'
                f'<div style="font-size:12px; color:{TEXT_SECONDARY}; line-height:1.6;">'
                f"{term['detail']}</div></div>",
                unsafe_allow_html=True,
            )

            st.markdown(
                f'<div style="background:{DEAD_ZONE_BG}; border-left:3px solid {DEAD_ZONE}; '
                f'border-radius:0 6px 6px 0; padding:10px 14px; margin-bottom:6px;">'
                f'<div style="font-size:11px; font-weight:600; color:{DEAD_ZONE}; '
                f'text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;">Think of it as…</div>'
                f'<div style="font-size:12px; color:{TEXT_PRIMARY}; line-height:1.6;">'
                f"{term['analogy']}</div></div>",
                unsafe_allow_html=True,
            )

            if term.get("example"):
                st.markdown(
                    f'<div style="background:{SURFACE}; border-left:3px solid {TEXT_TERTIARY}; '
                    f'border-radius:0 6px 6px 0; padding:10px 14px; margin-bottom:6px;">'
                    f'<div style="font-size:11px; font-weight:600; color:{TEXT_TERTIARY}; '
                    f'text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;">Example</div>'
                    f'<div style="font-size:12px; color:{TEXT_SECONDARY}; line-height:1.6; font-family:monospace;">'
                    f"{term['example']}</div></div>",
                    unsafe_allow_html=True,
                )

            st.markdown(
                f'<div style="background:#05271455; border-left:3px solid {BUY_GREEN}; '
                f'border-radius:0 6px 6px 0; padding:10px 14px;">'
                f'<div style="font-size:11px; font-weight:600; color:{BUY_GREEN}; '
                f'text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px;">How to use this</div>'
                f'<div style="font-size:12px; color:{TEXT_PRIMARY}; line-height:1.6;">'
                f"{term['how_to_use']}</div></div>",
                unsafe_allow_html=True,
            )
