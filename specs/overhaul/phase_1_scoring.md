# Phase 1 — Deterministic Scoring Rubric

```yaml
phase_id: phase_1
status: pending
depends_on: [phase_0, phase_3a]
blocks: [phase_2, phase_4a, phase_4_5, phase_7, dashboard]
estimated_effort: 4 days
test_framework: pytest
```

## Goal

Replace the LLM-decided composite score with a deterministic weighted formula over measurable signals. The current synthesizer at `src/plutus/agents/prompts.py:110–146` is an LLM that gates `BUY` on `technical >= 6 AND sentiment >= 0 AND risk = ACCEPTABLE`. Because data sources are partially stubbed, the gate rarely passes and the LLM defaults to mid-range `WATCH`. This phase moves the score to a pure function, shrinks the LLM to narrative-writing duty, and produces a measurable score that can be backtested per bucket.

After this phase: a 5-symbol fixture (`RELIANCE, HDFCBANK, BHARTIARTL, INFY, TATAMOTORS`) produces composite scores spanning a ≥40-point range with at least one `BUY`, two `HOLD`, and one `AVOID`. The all-`WATCH` failure mode is dead.

## Acceptance criteria

- [ ] `pytest tests/test_scoring/` — all tests green
- [ ] Score range on 5-symbol fixture spans ≥ 40 points (e.g., 25–75 not 45–55)
- [ ] Fixture produces ≥ 1 `BUY`, ≥ 2 `HOLD`, ≥ 1 `AVOID` — not all `WATCH`
- [ ] LLM synthesizer no longer emits `recommendation` or `confidence` — those fields come from `scoring.py`
- [ ] All five sub-scores (Tech, SmartMoney, Sentiment, Regime, RR) persist to `Recommendation` table (columns already exist at `src/plutus/db/models.py:90–92`; just populate)
- [ ] Material negative event forces `AVOID` regardless of other pillars
- [ ] R:R < 2.0 zeros the RR pillar

## Prerequisites

- Phase 0 done — backtest produces sane numbers (Technical pillar consumes `best-bundle Sharpe`)
- Phase 3a done — `get_nifty_regime()` and `get_sector_strength()` exist (Regime pillar consumes them)
- Phase 3b in progress is OK — SmartMoney pillar gracefully degrades when Tickertape returns `UNKNOWN`

## Task list

### TASK-1.1 — Lock the score schema

```yaml
parallelizable: no
parallel_group: null
reason: All pillar implementations consume this type.
estimated_effort: 30min
```

**Test first**:
```python
# tests/test_scoring/test_schema.py (new)
from plutus.agents.scoring import ScoreBreakdown, Classification

def test_score_breakdown_immutable_dataclass():
    b = ScoreBreakdown(technical=80, smart_money=50, sentiment=60, regime=70, rr=90)
    assert b.composite == round(80*0.40 + 50*0.15 + 60*0.15 + 70*0.15 + 90*0.15)
    assert isinstance(b.composite, int)

def test_classification_enum_values():
    assert {c.value for c in Classification} == {"BUY", "WATCH", "HOLD", "AVOID"}
```

**Files to create**:
- `src/plutus/agents/scoring.py` (new) — type definitions:
  ```python
  from dataclasses import dataclass, field
  from enum import Enum

  class Classification(str, Enum):
      BUY = "BUY"
      WATCH = "WATCH"
      HOLD = "HOLD"
      AVOID = "AVOID"

  PILLAR_WEIGHTS = {"technical": 0.40, "smart_money": 0.15, "sentiment": 0.15, "regime": 0.15, "rr": 0.15}

  @dataclass(frozen=True)
  class ScoreBreakdown:
      technical: float    # 0-100
      smart_money: float
      sentiment: float
      regime: float
      rr: float
      hard_avoid_reasons: tuple[str, ...] = field(default_factory=tuple)

      @property
      def composite(self) -> int:
          weighted = sum(getattr(self, k) * w for k, w in PILLAR_WEIGHTS.items())
          return round(weighted)
  ```

**Acceptance**:
- [ ] `pytest tests/test_scoring/test_schema.py` green
- [ ] Weights sum to 1.0

---

### TASK-1.2 — Build the test fixture

```yaml
parallelizable: no
parallel_group: null
reason: All pillar tests consume the same fixture; build once, share.
estimated_effort: 1h
```

**Test first** (this task IS the fixture, but it must round-trip):
```python
# tests/conftest.py (extend)
import pandas as pd
import pytest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ohlcv"

@pytest.fixture
def fixture_symbol_ohlcv():
    """Returns dict[symbol, DataFrame] for the 5 fixture stocks."""
    symbols = ["RELIANCE", "HDFCBANK", "BHARTIARTL", "INFY", "TATAMOTORS"]
    return {s: pd.read_parquet(FIXTURE_DIR / f"{s}_90d.parquet") for s in symbols}

@pytest.fixture
def fixture_indicators(fixture_symbol_ohlcv):
    from plutus.data.ohlcv import add_indicators
    return {s: add_indicators(df) for s, df in fixture_symbol_ohlcv.items()}

# tests/test_scoring/test_fixture.py
def test_fixture_loads_all_5_symbols(fixture_symbol_ohlcv):
    assert set(fixture_symbol_ohlcv.keys()) == {"RELIANCE", "HDFCBANK", "BHARTIARTL", "INFY", "TATAMOTORS"}
    for sym, df in fixture_symbol_ohlcv.items():
        assert len(df) >= 60, f"{sym}: fewer than 60 bars"

def test_fixture_indicators_complete(fixture_indicators):
    for sym, df in fixture_indicators.items():
        for col in ["EMA_20", "EMA_50", "EMA_200", "RSI_14", "ATRr_14", "Volume_Ratio"]:
            assert col in df.columns, f"{sym} missing {col}"
```

**Files to create**:
- `tests/fixtures/ohlcv/*.parquet` — 5 files, one per symbol, 90 bars from a fixed historical window (e.g., `2025-09-01` to `2025-12-31`).
- `scripts/build_test_fixtures.py` — one-shot script that fetches the data and writes the parquets. Run once during phase setup.

**Implementation steps**:
1. Write `scripts/build_test_fixtures.py` invoking `fetch_ohlcv` for each symbol over a fixed historical window.
2. Run the script; commit the parquets (~50KB each).
3. Add the fixtures above to `conftest.py`.

**Acceptance**:
- [ ] `tests/fixtures/ohlcv/` contains 5 parquet files
- [ ] `pytest tests/test_scoring/test_fixture.py` green

---

### Parallel group 1A — Pillar implementations (TASK-1.3 through TASK-1.7)

The five pillars are independent pure functions over the same input. **Dispatch to subagents in parallel.**

### TASK-1.3 — Technical pillar (40%)

```yaml
parallelizable: yes
parallel_group: 1A
reason: Pure function over indicator DataFrame; no shared state with other pillars.
estimated_effort: 4h
```

**Test first**:
```python
# tests/test_scoring/test_pillar_technical.py
import pytest
from plutus.agents.scoring import technical_pillar

def test_perfect_uptrend_scores_high(fixture_indicators):
    # construct synthetic "all stars align" frame: EMA20>EMA50>EMA200, RSI 60, Volume_Ratio 2.0, MACD positive
    ...
    score = technical_pillar(df, best_bundle_sharpe=2.5)
    assert score >= 75

def test_downtrend_scores_low(fixture_indicators):
    score = technical_pillar(df_downtrend, best_bundle_sharpe=-1.5)
    assert score <= 30

def test_pillar_returns_0_100_range(fixture_indicators):
    for sym, df in fixture_indicators.items():
        score = technical_pillar(df, best_bundle_sharpe=1.0)
        assert 0 <= score <= 100

def test_rsi_oversold_in_downtrend_penalised():
    # confirms we don't conflate "oversold = buy" with "oversold in confirmed downtrend = stay out"
    ...
```

**Files to modify/create**:
- `src/plutus/agents/scoring.py` — add `technical_pillar(df, best_bundle_sharpe) -> float`
- Sub-components (each 0-100, then weighted):
  - `trend_alignment` (30% of pillar): `EMA20 > EMA50 > EMA200` ⇒ 100; partial alignment ⇒ proportional; bearish stack ⇒ 0
  - `momentum` (25%): RSI 50–70 ⇒ 80–100; RSI 30–50 ⇒ 30–60; RSI > 70 ⇒ 50 (overbought caution); RSI < 30 in uptrend ⇒ 70 (oversold-in-uptrend bonus)
  - `volume_confirmation` (15%): `Volume_Ratio >= 1.5` ⇒ 100; `>= 1.3` ⇒ 70; `< 1.0` ⇒ 0
  - `macd_signal` (15%): histogram trending up & positive ⇒ 100; flat ⇒ 50; trending down & negative ⇒ 0
  - `backtest_validation` (15%): clamp `best_bundle_sharpe` to [-2, +3], linearly map to 0–100

**Implementation steps**:
1. Implement each sub-component as a private `_<name>(df) -> float` function.
2. `technical_pillar` weights them and returns the sum.
3. All tests green.

**Acceptance**:
- [ ] Sub-component functions unit-tested individually
- [ ] On the 5-symbol fixture, technical scores span ≥ 30 points

---

### TASK-1.4 — Smart Money pillar (15%)

```yaml
parallelizable: yes
parallel_group: 1A
reason: Pure function over (FII/DII flow dict, MF holdings dict); independent of other pillars.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_scoring/test_pillar_smart_money.py
from plutus.agents.scoring import smart_money_pillar

def test_fii_dii_both_buying_max_score():
    score = smart_money_pillar(
        fii={"fii_net_cr": 5000, "fii_signal": "net_buyer"},
        dii={"dii_net_cr": 3000, "dii_signal": "net_buyer"},
        mf={"verdict": "ACCUMULATING", "mf_count_accumulating": 5, "mf_count_reducing": 0},
    )
    assert score >= 85

def test_both_selling_min_score():
    score = smart_money_pillar(
        fii={"fii_signal": "net_seller"}, dii={"dii_signal": "net_seller"},
        mf={"verdict": "REDUCING", "mf_count_accumulating": 0, "mf_count_reducing": 4},
    )
    assert score <= 25

def test_unknown_mf_degrades_gracefully():
    # When Tickertape returns UNKNOWN (Phase 3b not deployed yet)
    score = smart_money_pillar(
        fii={"fii_signal": "net_buyer"}, dii={"dii_signal": "neutral"},
        mf={"verdict": "UNKNOWN", "mf_count_accumulating": 0, "mf_count_reducing": 0},
    )
    # Should land in the middle, not penalised by absence
    assert 40 <= score <= 60
```

**Files to modify**:
- `src/plutus/agents/scoring.py` — add `smart_money_pillar(fii, dii, mf) -> float`
- Sub-scoring (each 0-100):
  - `institutional_flow_bias` (60% of pillar): both net_buyer ⇒ 100; one ⇒ 65; mixed ⇒ 50; both seller ⇒ 0
  - `mf_holdings_delta` (40%): when MF verdict ≠ `UNKNOWN`: `ACCUMULATING` ⇒ 90; `REDUCING` ⇒ 10; `NEUTRAL` ⇒ 50. When `UNKNOWN` (fallback): 50.

**Acceptance**:
- [ ] All three tests green
- [ ] `UNKNOWN` MF case never returns < 40 or > 60 (graceful degradation)

---

### TASK-1.5 — Sentiment pillar (15%)

```yaml
parallelizable: yes
parallel_group: 1A
reason: Pure function over news classifier output.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_scoring/test_pillar_sentiment.py
from plutus.agents.scoring import sentiment_pillar

def test_positive_no_material_scores_high():
    score = sentiment_pillar(
        news={"sentiment_score": 4.0, "sentiment_label": "positive",
              "is_material_event": False, "material_event_type": None},
    )
    assert score >= 70

def test_negative_material_zeros_pillar():
    score = sentiment_pillar(
        news={"sentiment_score": -3.0, "sentiment_label": "negative",
              "is_material_event": True, "material_event_type": "regulatory"},
    )
    assert score == 0

def test_positive_material_capped_below_max():
    # Earnings beat is positive AND material — but caps to 85 (still elevated, not extreme)
    score = sentiment_pillar(
        news={"sentiment_score": 4.5, "sentiment_label": "positive",
              "is_material_event": True, "material_event_type": "earnings"},
    )
    assert 70 <= score <= 90

def test_no_news_returns_neutral():
    score = sentiment_pillar(news={"sentiment_score": 0, "sentiment_label": "neutral",
                                    "is_material_event": False, "material_event_type": None})
    assert 45 <= score <= 55
```

**Files to modify**:
- `src/plutus/agents/scoring.py` — add `sentiment_pillar(news) -> float`
- Rules:
  - If `is_material_event` and sentiment is `negative` ⇒ return 0 AND emit hard_avoid_reason `material_negative_event`
  - Else: linearly map `sentiment_score` from -5..+5 to 0..100, capping at 85 if material positive

**Acceptance**:
- [ ] All four tests green
- [ ] Material negative event surfaced in `ScoreBreakdown.hard_avoid_reasons`

---

### TASK-1.6 — Regime pillar (15%)

```yaml
parallelizable: yes
parallel_group: 1A
reason: Pure function over Nifty regime + sector strength dicts.
estimated_effort: 2h
```

**Prerequisites**: Phase 3a complete.

**Test first**:
```python
# tests/test_scoring/test_pillar_regime.py
from plutus.agents.scoring import regime_pillar

def test_bull_regime_top_sector_max_score():
    score = regime_pillar(
        nifty_regime={"trend": "BULL", "slope": 0.5, "distance_from_ema50_pct": 3.5},
        sector="IT", sector_rs={"IT": 1.18, "PHARMA": 0.92, ...},
    )
    assert score >= 80

def test_bear_regime_weak_sector_min_score():
    score = regime_pillar(
        nifty_regime={"trend": "BEAR", "slope": -0.4, "distance_from_ema50_pct": -2.1},
        sector="METAL", sector_rs={"IT": 1.18, "METAL": 0.78, ...},
    )
    assert score <= 25

def test_sideways_regime_moderate():
    score = regime_pillar(
        nifty_regime={"trend": "SIDEWAYS", "slope": 0.0, "distance_from_ema50_pct": 0.2},
        sector="FMCG", sector_rs={"FMCG": 1.00, ...},
    )
    assert 40 <= score <= 60
```

**Files to modify**:
- `src/plutus/agents/scoring.py` — add `regime_pillar(nifty_regime, sector, sector_rs) -> float`
- Sub-scoring:
  - `nifty_component` (60%): BULL ⇒ 90 + 10×normalized_slope; SIDEWAYS ⇒ 50; BEAR ⇒ max(0, 30 - |slope|×30)
  - `sector_component` (40%): sector RS rank ⇒ percentile; top 3 ⇒ 100, top 6 ⇒ 75, bottom 3 ⇒ 0

**Acceptance**:
- [ ] All three tests green
- [ ] On 5-symbol fixture, BHARTIARTL (Telecom typically a "neutral" sector) scores 40–70

---

### TASK-1.7 — Risk/Reward pillar (15%)

```yaml
parallelizable: yes
parallel_group: 1A
reason: Pure function over (entry, stop, target1, target2) tuple.
estimated_effort: 1h
```

**Test first**:
```python
# tests/test_scoring/test_pillar_rr.py
from plutus.agents.scoring import rr_pillar

def test_rr_below_2_zeros():
    assert rr_pillar(entry=100, stop=98, t1=103, t2=104) == 0   # R:R = 1.5

def test_rr_2_to_3_linear_ramp():
    # R:R = 2.0 ⇒ ~0 just-above; R:R = 3.0 ⇒ 100
    assert rr_pillar(entry=100, stop=98, t1=104, t2=106) == pytest.approx(0, abs=5)   # R:R=2.0
    assert rr_pillar(entry=100, stop=98, t1=106, t2=108) == pytest.approx(100, abs=5) # R:R=3.0

def test_rr_above_3_capped_at_100():
    assert rr_pillar(entry=100, stop=98, t1=110, t2=115) == 100   # R:R=5.0

def test_negative_entry_safe():
    # Edge case: malformed inputs shouldn't crash
    assert rr_pillar(entry=0, stop=0, t1=0, t2=0) == 0
```

**Files to modify**:
- `src/plutus/agents/scoring.py` — add `rr_pillar(entry, stop, t1, t2) -> float`
- Formula:
  ```python
  risk = abs(entry - stop)
  reward = abs(t1 - entry)
  if risk == 0: return 0
  ratio = reward / risk
  if ratio < 2.0: return 0
  return min(100.0, (ratio - 2.0) * 100.0)
  ```

**Acceptance**:
- [ ] All four tests green
- [ ] R:R floor enforced at 2.0 (matches Phase 2 bundle gate)

---

### TASK-1.8 — Composite + classification

```yaml
parallelizable: no
parallel_group: null
reason: Sequential after parallel group 1A; needs all pillar functions.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_scoring/test_composite.py
from plutus.agents.scoring import compute_score, Classification

def test_compute_score_spreads_on_fixture(fixture_indicators, regime_stub, news_stub, smart_money_stub, levels_stub):
    scores = {}
    for sym in fixture_indicators:
        breakdown, cls = compute_score(sym, fixture_indicators[sym], levels_stub[sym], ...)
        scores[sym] = breakdown.composite

    # The headline acceptance criterion
    assert max(scores.values()) - min(scores.values()) >= 40

def test_classification_thresholds():
    from plutus.agents.scoring import _classify, ScoreBreakdown
    b75 = ScoreBreakdown(80, 70, 70, 70, 80)   # composite ~75
    b60 = ScoreBreakdown(60, 60, 60, 60, 60)
    b40 = ScoreBreakdown(40, 40, 40, 40, 40)
    b20 = ScoreBreakdown(20, 20, 20, 20, 20)
    assert _classify(b75, position_size=10, material_negative=False, regime_bear=False) == Classification.BUY
    assert _classify(b60, position_size=10, material_negative=False, regime_bear=False) == Classification.WATCH
    assert _classify(b40, position_size=10, material_negative=False, regime_bear=False) == Classification.HOLD
    assert _classify(b20, position_size=10, material_negative=False, regime_bear=False) == Classification.AVOID

def test_material_negative_forces_avoid():
    high_score = ScoreBreakdown(95, 90, 0, 90, 95, hard_avoid_reasons=("material_negative_event",))
    assert _classify(high_score, position_size=10, material_negative=True, regime_bear=False) == Classification.AVOID

def test_rr_below_2_forces_no_buy():
    b80 = ScoreBreakdown(95, 90, 90, 90, 0)   # composite is high but RR=0
    # Composite would be 88.5×0.85 ≈ 75 (high) BUT RR pillar zero ⇒ no BUY allowed
    cls = _classify(b80, position_size=10, material_negative=False, regime_bear=False, rr_pillar_score=0)
    assert cls != Classification.BUY

def test_zero_position_size_blocks_buy():
    b80 = ScoreBreakdown(95, 90, 90, 90, 95)
    cls = _classify(b80, position_size=0, material_negative=False, regime_bear=False)
    assert cls != Classification.BUY
```

**Files to modify**:
- `src/plutus/agents/scoring.py` — add:
  ```python
  def compute_score(symbol, indicator_df, levels, news, fii, dii, mf,
                    nifty_regime, sector, sector_rs, best_bundle_sharpe, position_size):
      tech = technical_pillar(indicator_df, best_bundle_sharpe)
      sm = smart_money_pillar(fii, dii, mf)
      sent = sentiment_pillar(news)
      reg = regime_pillar(nifty_regime, sector, sector_rs)
      rr = rr_pillar(levels.entry, levels.stop, levels.t1, levels.t2)
      hard_avoid = tuple(...)
      breakdown = ScoreBreakdown(tech, sm, sent, reg, rr, hard_avoid_reasons=hard_avoid)
      cls = _classify(breakdown, position_size, ...)
      return breakdown, cls

  def _classify(breakdown, position_size, material_negative, regime_bear, ...) -> Classification:
      if material_negative or breakdown.composite < 35: return AVOID
      if regime_bear: return AVOID
      if breakdown.composite >= 70 and breakdown.rr > 0 and position_size > 0:
          return BUY
      if breakdown.composite >= 55: return WATCH
      if breakdown.composite >= 35: return HOLD
      return AVOID
  ```

**Acceptance**:
- [ ] All composite tests green
- [ ] 5-symbol fixture spread ≥ 40 points (the headline criterion)

---

### TASK-1.9 — Shrink the synthesizer LLM prompt

```yaml
parallelizable: no
parallel_group: null
reason: Synthesizer rewrite depends on compute_score being callable.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_scoring/test_synthesizer.py
from plutus.agents.synthesizer import run_synthesis

def test_synthesis_does_not_emit_recommendation(monkeypatch):
    """LLM narrative must NOT include recommendation/confidence — those come from scoring."""
    # Mock the LLM call and the score
    ...
    out = run_synthesis(symbol="RELIANCE", breakdown=..., classification=Classification.WATCH,
                        technical_output=..., sentiment_output=..., smart_money_output=...)
    assert "recommendation" not in out          # never emits it
    assert "narrative" in out
    assert "top_3_risk_flags" in out
    assert isinstance(out["top_3_risk_flags"], list)
    assert len(out["top_3_risk_flags"]) <= 3
```

**Files to modify**:
- `src/plutus/agents/prompts.py:110–146` — `SYNTHESIZER_PROMPT` shrinks to:
  ```
  SYNTHESIZER_PROMPT = """You are the chief investment narrator for a retail trader in India.
  You receive a deterministic score breakdown and write a 150-250 word thesis.

  DO NOT decide recommendation or score — both are passed in and final.

  Output JSON:
  {
    "narrative": <150-250 word thesis>,
    "top_3_risk_flags": [<list of up to 3 short risk strings>]
  }

  Mention in the narrative: technical setup, sentiment context, smart-money signal, key risk.
  Be specific: cite actual price levels and patterns from the inputs.
  """
  ```
- `src/plutus/agents/synthesizer.py` — adapt the public function:
  ```python
  def run_synthesis(symbol, breakdown, classification, **agent_outputs) -> dict:
      narrative_payload = _call_llm(prompt=SYNTHESIZER_PROMPT, inputs={
          "symbol": symbol,
          "breakdown": asdict(breakdown),
          "classification": classification.value,
          **agent_outputs,
      })
      return {
          "narrative": narrative_payload["narrative"],
          "top_3_risk_flags": narrative_payload["top_3_risk_flags"],
      }
  ```

**Acceptance**:
- [ ] Synthesizer test green
- [ ] No LLM output ever overrides `compute_score`'s decision

---

### TASK-1.10 — Wire scoring into the graph

```yaml
parallelizable: no
parallel_group: null
reason: graph.py orchestration depends on TASK-1.8 and TASK-1.9.
estimated_effort: 2h
```

**Test first**:
```python
# tests/test_scoring/test_graph_integration.py
from plutus.agents.graph import run_analysis

def test_run_analysis_returns_score_breakdown(monkeypatch):
    # Mock data fetches; assert that result has both deterministic score and narrative
    ...
    result = run_analysis(symbol="RELIANCE")
    assert "composite_score" in result
    assert "sub_scores" in result
    assert set(result["sub_scores"].keys()) == {"technical", "smart_money", "sentiment", "regime", "rr"}
    assert "narrative" in result
    assert "recommendation" in result
    assert result["recommendation"] in {"BUY", "WATCH", "HOLD", "AVOID"}
```

**Files to modify**:
- `src/plutus/agents/graph.py:162–293` — `synthesizer_node` becomes:
  ```python
  def scoring_node(state):
      breakdown, cls = compute_score(
          symbol=state["symbol"],
          indicator_df=state["indicator_df"],
          levels=state["technical_output"],
          news=state["sentiment_output"],
          fii=state["smart_money_output"]["fii"],
          dii=state["smart_money_output"]["dii"],
          mf=state["smart_money_output"]["mf"],
          nifty_regime=state["regime_output"]["nifty"],
          sector=state["regime_output"]["sector"],
          sector_rs=state["regime_output"]["sector_rs"],
          best_bundle_sharpe=state["best_bundle_sharpe"],
          position_size=state["risk_output"]["shares"],
      )
      return {"score_breakdown": breakdown, "classification": cls}

  def narrative_node(state):
      payload = run_synthesis(state["symbol"], state["score_breakdown"], state["classification"], ...)
      return {"narrative": payload["narrative"], "risk_flags": payload["top_3_risk_flags"]}
  ```
- Graph wiring: `... → scoring_node → narrative_node → END`

**Acceptance**:
- [ ] Integration test green
- [ ] `run_analysis` returns deterministic `recommendation` even when LLM narrative call is mocked

---

### TASK-1.11 — Persist sub-scores

```yaml
parallelizable: yes
parallel_group: 1B
reason: Independent of TASK-1.12; both touch persistence layer in non-overlapping ways.
estimated_effort: 1h
```

**Test first**:
```python
# tests/test_scoring/test_persistence.py
def test_recommendation_row_persists_sub_scores(db_session):
    from plutus.db.models import Recommendation
    rec = Recommendation(
        symbol="RELIANCE", technical_score=80, sentiment_score=60,
        smart_money_score=70, recommendation="BUY", confidence=75,
        # NEW columns (or repurposed):
        regime_score=80, rr_score=90,
    )
    db_session.add(rec); db_session.commit()
    row = db_session.query(Recommendation).filter_by(symbol="RELIANCE").one()
    assert row.regime_score == 80
    assert row.rr_score == 90
```

**Files to modify**:
- `src/plutus/db/models.py:70–106` — add `regime_score` and `rr_score` Float columns; verify `confidence` is used as `composite_score`.
- `src/plutus/db/schema.sql` — add columns.
- `migrations/00X_phase1_sub_scores.sql` (new) — `ALTER TABLE recommendations ADD COLUMN regime_score REAL; ADD COLUMN rr_score REAL;`

**Acceptance**:
- [ ] Migration runs without error on a fresh DB and on an existing one
- [ ] Test green

---

### TASK-1.12 — Remove the "BUY only if tech>=6 AND sentiment>=0" gate from all code paths

```yaml
parallelizable: yes
parallel_group: 1B
reason: Independent of TASK-1.11; touches prompts and graph but not DB.
estimated_effort: 30min
```

**Test first**:
```python
# tests/test_scoring/test_no_legacy_gate.py
import re
from pathlib import Path

def test_legacy_gate_absent_from_prompts():
    src = Path("src/plutus/agents/prompts.py").read_text()
    assert "technical score >= 6 AND sentiment >= 0" not in src
    assert "BUY only when" not in src
```

**Files to modify**:
- `src/plutus/agents/prompts.py:140` — delete the `CRITICAL RULES` block.
- Confirm nothing in `graph.py` or `synthesizer.py` re-implements the gate.

**Acceptance**:
- [ ] Grep returns no hits for `technical score >= 6`
- [ ] Test green

## Streamlit considerations

None for Phase 1 itself. The dashboard surfacing of sub-scores is owned by the Dashboard surfacing phase (`phase_dashboard.md`). However, **flag**: the Strategy Lab and Signals tabs read from `Recommendation` rows; the column additions in TASK-1.11 are picked up automatically if the dashboard does `pd.read_sql(...)`.

## Verification

End-to-end on the 5-symbol fixture:

```bash
pytest tests/test_scoring/ -v
python scripts/score_5_symbol_fixture.py    # prints score breakdown per symbol
```

Expected output:
- ≥ 1 symbol classified `BUY`
- ≥ 2 symbols classified `HOLD`
- ≥ 1 symbol classified `AVOID`
- `max(composite) - min(composite) >= 40`

## Done definition

- [ ] All 12 tasks complete and tests green
- [ ] 5-symbol fixture verification recorded in PR description
- [ ] `README.md` updated: Phase 1 status → `done`
- [ ] Phase 2, 4a, 4.5, 7, dashboard unblocked

## References

- Plan: `/Users/leander/.claude/plans/first-the-scale-you-hazy-naur.md` (Phase 1 section)
- Code anchors:
  - `src/plutus/agents/prompts.py:110–146` — SYNTHESIZER_PROMPT (target for shrink)
  - `src/plutus/agents/prompts.py:140` — the gate to remove
  - `src/plutus/agents/synthesizer.py:11–58` — LLM call site
  - `src/plutus/agents/graph.py:162–293` — orchestration
  - `src/plutus/db/models.py:70–106` — Recommendation model (sub-score columns exist; persist them)
  - `src/plutus/data/ohlcv.py:294` — `add_indicators()` (consumed by Technical pillar)
- Related phase docs:
  - [phase_3a_regime.md](phase_3a_regime.md) — feeds Regime pillar
  - [phase_3b_tickertape.md](phase_3b_tickertape.md) — feeds SmartMoney pillar
  - [phase_4a_outcomes.md](phase_4a_outcomes.md) — validates scoring per bucket
