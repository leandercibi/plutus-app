# TESTING

> How TDD is practiced in this project. Binding.

---

## 1. The order is non-negotiable

1. Open the spec doc for the module you are about to write.
2. Find the table of tests for that module.
3. Write the test file. The implementation file does not exist yet — `pytest` errors with `ImportError` or `AttributeError`. That's expected.
4. Write the minimum implementation that makes the test pass. No anticipated features.
5. Refactor only the green code you just wrote. Do not refactor adjacent code.
6. Repeat for the next test.

If you find yourself writing implementation before the test, stop. Delete what you wrote. Start over from the test.

---

## 2. Test tree mirrors source tree

For every `src/plutus/X/Y.py` there is a `tests/X/test_Y.py`. The script `scripts/check_test_mirror.py` runs in CI and fails the build if a source file has no test file.

Exceptions:
- `__init__.py` files are excluded.
- Pure-data modules with no logic (e.g., enums-only files) get a "smoke" test that just imports.

---

## 3. Fixtures, not mocks

Mocks lie. Fixtures pin reality.

Fixture catalog at `tests/fixtures/`:

```
tests/fixtures/
├── ohlcv/
│   ├── trend_pullback.parquet         # 90 days, clean trend pullback setup
│   ├── donchian_breakout.parquet      # breakout fixture
│   ├── reversal_engulfing.parquet
│   ├── vcp_3contractions.parquet
│   ├── circuit_hit_30d_ago.parquet    # for B7
│   └── ...
├── delivery/
│   ├── delivery_high_today.parquet
│   └── expiry_day.parquet
├── regime/
│   ├── bull_day.json
│   ├── bear_day.json
│   └── flip_day.json
├── fundamentals/
│   ├── high_quality.json
│   ├── value_trap.json                # for A12
│   └── base_effect_recovery.json      # for A12
├── calibration/
│   ├── n_5_small.json
│   ├── n_30_medium.json
│   └── n_200_large.json
├── headlines/
│   ├── two_independent_sources.json   # for A8 corroboration
│   ├── single_keyword_match.json
│   └── structural_event.json
└── cost_grid.json                     # broker grid for cost-model tests
```

Each fixture is small (≤ 100 KB), human-readable where possible, checked into git.

Mocks are reserved for one narrow case: external network endpoints (Telegram POST, OpenRouter API). Use `responses` or `respx` libraries; do not hand-roll `Mock()`.

---

## 4. Determinism

| Source of nondeterminism | Tool |
|---|---|
| `datetime.now()`, `date.today()` | `freezegun` |
| `random.*`, `np.random` | seed with explicit constants; expose seed as a function arg |
| Database insertion order | order by an explicit timestamp + id; never assume order |
| Float arithmetic in cost / R math | `Decimal` for cost, `pytest.approx` with explicit tolerance for R |
| Hypothesis-generated cases | `@settings(deterministic=True, derandomize=True)` |

Flaky tests are a stop-the-world bug. No retries. If a test flakes once, fix the cause that same hour.

---

## 5. Property-based tests

Use Hypothesis for:
- Cost model (any qty, price → positive cost; round-trip cost monotone in qty).
- Fill policy (no fill before next bar; gap-through never fills better than open).
- Slippage (monotone in qty/ADV and ATR).
- Expectancy gate (cost ↑ → expectancy ↓ holding other things equal).
- Tranche triggers (higher ATR → wider absolute % distance).

Property tests live next to example tests, suffix `_property`:

```
tests/shared/cost_model/
├── test_costs.py
└── test_costs_property.py
```

---

## 6. Markers and selection

```ini
# pytest.ini
[pytest]
markers =
    unit: fast, no IO, no DB
    integration: uses a real SQLite/postgres test DB
    property: hypothesis property tests
    slow: > 1s wall time; excluded from default run
    hallmark: a hallmark test traced back to a review item
testpaths = tests
addopts = -ra --strict-markers --strict-config
```

Daily CI runs `pytest -m "not slow"`. Pre-merge gate runs everything.

The `hallmark` marker is applied to every test named explicitly in a spec doc as a hallmark (e.g., A5, A16, B17). A separate CI job runs `pytest -m hallmark` and reports which review items are green.

---

## 7. Coverage

```
swing/         ≥ 90% line
accumulation/  ≥ 90%
shared/        ≥ 90%
backtesting/   ≥ 90%
data/          ≥ 80%
api/           ≥ 85%
dashboard/     ≥ 70% (UI render checks are coarse)
```

CI gate; falling below threshold fails the build. Coverage is a floor — never the goal.

---

## 8. What must be tested per class/method

A class is tested when:
- Each public method has at least one example test.
- Each public method with branching has tests on both branches.
- Each invariant (declared in docstring or spec doc) has a test that violates it and asserts the failure.
- Each public method that mutates state has a test for the post-state.
- Each public method that reads from DB has a test using a session fixture.

If you find a method without a test, you are not done. The spec doc lists every method that needs one; if the spec doc missed one, add to the spec first, then add the test, then the implementation.

---

## 9. Hallmark tests (one-page register)

The single most-important test per review item. Loss of any of these means the corresponding fix has regressed.

| Hallmark test | Review item |
|---|---|
| `test_fill_policy_stop_gap.py` | A1 |
| `test_pillars_no_per_stock_sharpe_leak.py` | A3 |
| `test_expectancy_primary_gate.py` | A4 |
| `test_composite_a5_hallmark.py` | A5 |
| `test_size_only_one_risk_constant.py` | A6 |
| `test_no_fii_dii_in_per_stock.py` | A7/C1 |
| `test_color_is_color_only.py` | A8/C6 |
| `test_pillars_technical.py` | A10 |
| `test_selector_default_composite_seed.py` | A11 |
| `test_valuation_cap.py` | A12 |
| `test_triggers.py` (ATR-normalized) | A13 |
| `test_tuner_objective_is_expectancy.py` | A14/C5 |
| `test_jobs_monday_revalidation.py` | A15 |
| `test_monitor_sl_breach_always_fires.py` | A16 |
| `test_universe_pit.py` | A17 |
| `test_postmortem_three_benchmarks.py` | B2 |
| `test_thesis_invalidation.py` | B9 |
| `test_mock_vs_real.py` | B10 |
| `test_freshness.py` | B11 |
| `test_signals_dead_zone_shows_buy_watch.py` | B17 |
| `test_strategy_lab_smc_display_only.py` | C3 |

---

## 10. Test naming convention

`test_<unit>_<condition>_<expected>.py` — or close to it.

Good:
- `test_fill_policy_stop_gap.py`
- `test_corroboration_two_headlines_fires.py`
- `test_drawdown_governor_restores_after_three_days.py`

Bad:
- `test_fills.py` (too vague)
- `test_works.py` (no contract)

Inside a file, test functions follow the same shape: `test_<scenario>_<expected>`.

---

## 11. CI pipeline (binding)

```
1. ruff check
2. mypy --strict
3. import-linter
4. scripts/check_test_mirror.py
5. pytest -m "not slow" with coverage
6. pytest -m "hallmark"
7. pytest -m "slow" (separate stage)
8. alembic upgrade from empty DB
9. dashboard AppTest smoke
10. coverage gate
```

Any failure blocks merge.

---

## 12. Anti-patterns (caught in review)

- Tests that assert no exception is raised and nothing else.
- Tests that mock the thing they're testing.
- Tests with `time.sleep` or `retry` loops.
- Tests that depend on test execution order.
- Tests with magic numbers — every constant in a test has a comment or a fixture.
- Tests that compare floats with `==`.
- Tests inside `try/except` that swallow.
