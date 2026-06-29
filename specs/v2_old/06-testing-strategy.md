# 06 — Testing strategy

## Principles

1. **Test first.** For every new public function in phases 02–05, the failing test exists before the implementation. No exceptions.
2. **Unit > integration > e2e.** Many small unit tests over a few large integration tests. Unit = pure functions or single ORM round-trip. Integration = pipeline calling multiple modules. E2E = scheduler firing a full weekly run.
3. **Boundary mocks only.** Network (yfinance, AngelOne, NSE API, OpenRouter), filesystem (cache dirs), and time (`datetime.utcnow`) are the only things that get mocked. Everything else runs real.
4. **In-memory SQLite for DB tests.** No fixtures touch the real PostgreSQL. The in-memory DB is created per test via the `in_memory_db` fixture.
5. **Determinism.** No `random` without a seed. No `datetime.now()` without `freeze_time`. A test that flakes once is fixed, not retried.

## Coverage targets

| Module | Min line coverage | Why this target |
|---|---|---|
| `core/data/fundamentals.py` | 95% | Pure logic + cache code, fully testable |
| `accumulation/scoring.py` | 100% | Pure functions, every branch hit |
| `accumulation/tranches.py` | 95% | DB layer + invariant logic |
| `accumulation/candidates.py` | 85% | Big function with many data dependencies |
| `accumulation/pipeline.py` | 80% | Orchestrator, mostly delegation |
| `accumulation/triggers.py` | 90% | Critical correctness path |
| `dashboard/components/*` | 70% | UI; smoke tests cover most |
| `dashboard/*.py` (views) | 50% | Mostly Streamlit calls, hard to assert |

Run: `pytest --cov=src/plutus --cov-report=term-missing`. Fail the CI gate if any of the above drops below target.

## Test layout

```
tests/
├── conftest.py                       ← global fixtures
├── fixtures/                         ← seed data (CSVs, JSON snapshots)
│   ├── nifty100_sample.csv
│   ├── ohlcv_hdfcbank_30d.json
│   ├── fundamentals_strong.json
│   └── fundamentals_weak.json
├── mocks/
│   ├── __init__.py
│   ├── mock_yfinance.py
│   ├── mock_angelone.py
│   ├── mock_openrouter.py
│   └── mock_channel.py
├── core/
│   ├── test_public_surface.py
│   ├── test_config.py
│   ├── test_config_params.py
│   ├── test_models_shared.py
│   ├── test_alerts_monitor.py
│   └── data/
│       ├── test_ohlcv.py             ← moved from tests/test_data_ohlcv.py
│       ├── test_regime.py            ← moved from tests/test_regime/
│       ├── test_regime_subscription.py
│       ├── test_smart_money.py
│       ├── test_tickertape.py        ← moved from tests/test_tickertape/
│       ├── test_universe.py
│       ├── test_news.py              ← moved from tests/test_data_news.py
│       └── test_fundamentals.py      ← NEW
├── swing/
│   ├── test_public_surface.py
│   ├── test_pipeline.py
│   ├── test_triggers.py              ← from tests/test_phase8a_alerts.py
│   ├── test_scoring/                 ← moved from tests/test_scoring/
│   ├── test_strategies/              ← moved from tests/test_strategies.py + test_bundle_hardening
│   ├── test_backtesting/             ← moved from tests/test_backtesting.py + test_walk_forward
│   ├── test_outcomes/                ← moved from tests/test_outcomes/
│   ├── test_postmortem/              ← moved from tests/test_self_finetuning/
│   └── test_portfolio.py             ← moved from tests/test_phase7_portfolio_analyze.py
├── accumulation/
│   ├── test_scoring.py               ← 23 tests (see 04.2)
│   ├── test_models.py                ← 5 tests (see 04.3)
│   ├── test_tranches.py              ← 8 tests (see 04.4)
│   ├── test_candidates.py            ← 3 tests (see 04.5)
│   ├── test_pipeline.py              ← 2 tests (see 04.6)
│   └── test_triggers.py              ← 7 tests (see 04.7)
├── api/
│   ├── test_routes_swing.py
│   └── test_routes_accumulation.py
├── dashboard/
│   ├── test_components.py
│   ├── test_helpers.py
│   ├── test_views.py
│   └── test_buttons_interactive.py   ← from project root (if salvageable)
└── integration/
    ├── test_weekly_run_end_to_end.py
    ├── test_regime_flip_triggers_bull_ready.py
    └── test_tranche_alert_chain.py
```

## Required fixtures

### Global (`tests/conftest.py`)

```python
@pytest.fixture
def in_memory_db():
    """Per-test SQLite in-memory DB with all migrations applied."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import sessionmaker
    from plutus.core.db.base import Base
    engine = create_engine("sqlite:///:memory:",
                            connect_args={"check_same_thread": False},
                            poolclass=StaticPool)
    Base.metadata.create_all(engine)
    _apply_all_migrations(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close(); engine.dispose()

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Sets required env vars so plutus.core.config.Settings() doesn't raise."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-api-key-12345")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")

@pytest.fixture
def freeze_now(monkeypatch):
    """Pin datetime.utcnow / datetime.now to 2026-06-10 12:00 UTC."""
    import datetime as _dt
    fixed = _dt.datetime(2026, 6, 10, 12, 0, 0)
    class FrozenDateTime(_dt.datetime):
        @classmethod
        def utcnow(cls): return fixed
        @classmethod
        def now(cls, tz=None): return fixed
    monkeypatch.setattr("datetime.datetime", FrozenDateTime)
    return fixed
```

### Mock yfinance (`tests/mocks/mock_yfinance.py`)

```python
class MockYFinance:
    def __init__(self):
        self.data = {}              # symbol -> info dict
        self._fail = False
        self._fail_next = False

    def set(self, symbol: str, info: dict) -> None:
        self.data[symbol] = info

    def always_fail(self) -> None:
        self._fail = True

    def fail_next(self) -> None:
        self._fail_next = True

    def _ticker(self, symbol: str):
        if self._fail or self._fail_next:
            self._fail_next = False
            raise ConnectionError("mock yfinance fail")
        info = self.data.get(symbol, {})
        ticker = type("T", (), {"info": info})()
        return ticker

@pytest.fixture
def mock_yfinance(monkeypatch):
    m = MockYFinance()
    monkeypatch.setattr("yfinance.Ticker", m._ticker)
    return m
```

### Mock OpenRouter (`tests/mocks/mock_openrouter.py`)

```python
@pytest.fixture
def fake_llm(monkeypatch):
    """Stubs openrouter_client.call_llm to return a deterministic JSON blob."""
    def _fake_call(messages, model, response_format=None, temperature=0.2):
        sys_msg = messages[0]["content"] if messages else ""
        # crude routing by agent
        if "technical" in sys_msg.lower():
            return '{"trend":"BULL","entry":1000,"stop":950,"target1":1100,"target2":1200,"confidence":0.7}'
        if "risk" in sys_msg.lower():
            return '{"position_size":10,"max_loss_inr":500,"risk_status":"ACCEPTABLE"}'
        return '{"narrative":"…"}'
    monkeypatch.setattr("plutus.core.llm.openrouter_client.call_llm", _fake_call)
```

### Mock data layer (`tests/mocks/mock_data_layer.py`)

```python
class MockDataLayer:
    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self._universe = []
        self._fundamentals = {}
        self._no_ohlcv = set()

    def universe(self, syms): self._universe = syms; self._patch_universe()
    def fundamentals(self, mapping): self._fundamentals = mapping; self._patch_fund()
    def no_ohlcv(self, sym): self._no_ohlcv.add(sym); self._patch_ohlcv()
    def _patch_universe(self):
        self.monkeypatch.setattr("plutus.core.data.universe.get_universe",
                                  lambda kind="swing": self._universe)
    def _patch_fund(self):
        self.monkeypatch.setattr("plutus.core.data.fundamentals.get_fundamentals",
                                  lambda s: self._fundamentals.get(s))
    def _patch_ohlcv(self):
        def _load(sym, **kw):
            if sym in self._no_ohlcv: return None
            return _make_indicator_df(sym)  # 90 days of synthetic OHLCV with indicators
        self.monkeypatch.setattr("plutus.core.data.ohlcv.load_ohlcv", _load)

@pytest.fixture
def mock_data_layer(monkeypatch):
    return MockDataLayer(monkeypatch)
```

### Mock channel (`tests/mocks/mock_channel.py`)

```python
class FakeChannel:
    def __init__(self):
        self.sent = []
    def send(self, message: str) -> bool:
        self.sent.append(message); return True

@pytest.fixture
def fake_channel():
    return FakeChannel()
```

## Naming convention

Every test name reads as `test_{condition}_{expected_behaviour}`:

- Good: `test_pre_sl_warning_fires_when_ltp_within_1pct`
- Good: `test_create_position_duplicate_open_raises`
- Bad: `test_position_1`
- Bad: `test_things_work`

This style makes test failures self-describing in CI output.

## What never gets a unit test

- File moves (phase 01). The acceptance is "the full suite still passes after the move."
- Pure data classes with no logic (dataclasses are tested transitively by the functions that use them).
- Generated migrations (the apply-test covers them).

## What always gets a unit test

- Every new public function in `core/data/`, `accumulation/`, `swing/scoring`, `swing/triggers`, `accumulation/triggers`.
- Every classification branch (one test per branch).
- Every validator (one test per accept case, one per reject case).
- Every alert type (one test that it fires, one that it dedupes).
- Every DB invariant (uniqueness, FK, NOT NULL — at least the ones that load-bearing code depends on).

## Integration tests (3 mandatory)

`tests/integration/test_weekly_run_end_to_end.py`:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_weekly_run_swing_plus_accumulation(in_memory_db, mock_data_layer, fake_llm, mock_yfinance):
    """The Sunday 18:00 job runs both pipelines and writes both WeeklyRun + AccumulationRun rows."""
```

`tests/integration/test_regime_flip_triggers_bull_ready.py`:

```python
@pytest.mark.integration
def test_bear_to_bull_fires_bull_ready_on_open_accum_positions(in_memory_db, seeded_open_positions, fake_channel, monkeypatch):
    """Regime flip from BEAR to BULL triggers exactly one BULL_READY alert per qualifying position."""
```

`tests/integration/test_tranche_alert_chain.py`:

```python
@pytest.mark.integration
def test_position_creation_then_t2_alert_then_t2_logged(in_memory_db, fake_channel, monkeypatch):
    """Create position → drop price → run monitor → fire T2 alert → user logs T2 → no further T2 alerts fire."""
```

Run all integration tests with `pytest -m integration`. They are slower; CI runs them on push to main, dev runs them before requesting review.

## CI gate

`.github/workflows/ci.yml` (or equivalent) must:

1. `pip install -e .[dev]`
2. `pytest --cov=src/plutus --cov-report=xml --cov-fail-under=80`
3. `pytest -m integration` (separate job)
4. `ruff check src/ tests/` (or whatever linter the project picks — out of scope for v2 if none today)
5. Domain isolation lint:
   ```bash
   ! grep -rn "from plutus.swing" src/plutus/accumulation/ | grep -v "scoring.smart_money_pillar"
   ! grep -rn "from plutus.accumulation" src/plutus/swing/
   ! grep -rn "from plutus.swing\|from plutus.accumulation" src/plutus/core/
   ```

A failure in any of these blocks merge.

## What "thoroughly tested" means

The user asked for thorough testing of every function/class/method. The concrete bar:

- Every public function: ≥ 1 happy-path test + ≥ 1 failure-path test (or boundary case).
- Every classification enum: ≥ 1 test per outcome (BUY, WATCH, etc.).
- Every DB model: ≥ 1 round-trip test (create, query, delete).
- Every alert type: 1 fire test + 1 dedup test.
- Every dashboard view: 1 renders-clean smoke test.

If a function has no test, mark it `# pragma: no cover` only with a comment explaining why (e.g. `# pragma: no cover — entry point`). Otherwise add the test before merging.
