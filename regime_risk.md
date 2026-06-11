# Spec 06 — Shared Regime & Risk: Implementation Report

Branch: v2-rebuild. All TDD (test-first). `.venv/bin/python` used throughout.

## Result
- **35 tests pass** (`.venv/bin/python -m pytest tests/shared/regime/ tests/shared/risk/ -q`).
- **mypy --strict clean** on `src/plutus/shared/regime/` and `src/plutus/shared/risk/`.
- **ruff clean** on all new source + test files.

## Files created

### Regime (`src/plutus/shared/regime/`)
- `detector.py` — `RegimeInputs`, `RegimeVerdict`, `RegimeDetector.classify()` per §2 deterministic
  rules (BULL/BEAR/SIDEWAYS; confidence low/medium/high by satisfied sub-condition count;
  reasons list; breadth_confirmed via 5d breadth trend).
- `flip.py` — `RegimeFlipDetector.is_flip()` — True only when label changes AND
  `current.breadth_confirmed`.
- `snapshot.py` — `save_snapshot()` / `read_snapshot()` persist a `RegimeVerdict` + raw
  `RegimeInputs` to `db.RegimeSnapshot` and read back.

### Risk (`src/plutus/shared/risk/`)
- `types.py` — `OpenPosition(symbol, sector, risk_R, position_value_inr=None)`.
- `portfolio_heat.py` — `HeatInputs`, `HeatDecision`, `PortfolioHeat.evaluate()` with the
  correlation haircut `effective_risk_i = risk_i*(1+mean_corr_with_others)`; allowed iff
  `projected_heat_R <= settings.max_portfolio_heat_R`.
- `sector_cap.py` — `SectorCap.check()` → `CapDecision`; count cap (always) + pct-of-pool cap
  (when position values supplied).
- `correlation_guard.py` — `CorrelationGuard.check()` → `GuardDecision`; rejects if max pairwise
  60d-returns correlation with any open position exceeds `settings.pairwise_correlation_max`.
- `adv_cap.py` — `ADVCap.max_position_qty()` + `annotate()` (exact string
  `"position = X.X% of 20d ADV"`).
- `drawdown_governor.py` — `DrawdownGovernor.current_risk_multiplier()` + `record_close()`,
  persisting `db.DrawdownGovernorState`; 3-consecutive-recovery-day restore rule.
- `cash_position.py` — `CashAsPosition.decide()` → `CashDecision`; exact banner
  `"market offered K qualifying setups; X% of swing pool held in cash."`.
- `allocation.py` — `Allocation.desired_swing_pct()` (BULL 0.7 / SIDEWAYS 0.5 / BEAR 0.3) +
  `reallocate_uncommitted()` → `AllocationPlan`; committed capital never reduced.

## Acceptance criteria
- [x] FII/DII consumed only by `regime/detector.py` (+ persisted in `regime/snapshot.py`);
  grep confirms NO per-stock/risk module references FII/DII.
- [x] Heat / sector / correlation / ADV gates implemented and unit-tested.
- [x] Drawdown governor halves risk on triggered fixture; restores after 3 recovery days; stays
  halved on 2-days-then-dip.
- [x] Cash-as-position banner string matches the dashboard contract exactly.
- [x] Allocation never force-migrates committed swing or filled accumulation tranches.

## Decisions / deviations (surfaced, not silent)
1. **`RegimeInputs.pct_above_50dma_5d_ago` added (default 0.0).** The spec's `breadth_confirmed`
   requires "pct_above_50dma trend over 5d" but the listed dataclass only had a scalar
   `pct_above_50dma`. Added a prior-reading field (default keeps all spec fields intact) to
   compute the trend. **No change to settings.py / models.py / shared/types.py.**
2. **`OpenPosition.position_value_inr` added (default None).** The sector pct-of-pool cap needs
   per-position notional, which `risk_R` alone can't provide. Optional field; the count cap
   (the always-on check exercised by tests) works without it. This is a NEW file
   (`shared/risk/types.py`), not a modification to an existing shared type.
3. **`snapshot` maps `verdict.breadth_confirmed` → `RegimeSnapshot.breadth_confirmed_flip`.** The
   ORM column name differs from the verdict field; semantically the daily snapshot records whether
   breadth confirmed the regime. Round-trip test asserts this.
4. **SIDEWAYS confidence = "low".** Spec ties confidence to satisfied-rule count for the matched
   label; SIDEWAYS is the fallthrough (no full rule set matched), so low confidence.

## No blockers. No changes needed to settings.py, models.py, or shared/types.py.
