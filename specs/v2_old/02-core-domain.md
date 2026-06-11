# 02 — Core domain (shared infrastructure)

## Goal

After phase 01 moved files into `src/plutus/core/`, this phase ensures the core layer is a clean shared platform that both `swing/` and `accumulation/` can build on without circular imports.

This phase is mostly **verification + small splits**. It does not introduce new business logic.

## Scope

| Module | Responsibility | New work in this phase |
|---|---|---|
| `core/config.py` | Pydantic Settings, env-var loading | none — only update imports |
| `core/config_params.py` | DB-backed editable params | extend with accumulation knobs (07.x — defer to that phase) |
| `core/llm/openrouter_client.py` | OpenRouter HTTP client + `_parse_llm_json` | none |
| `core/data/ohlcv.py` | Market data fetch with AngelOne / Jugaad / yfinance fallback | none — frozen per rule A |
| `core/data/regime.py` | `get_nifty_regime()`, `get_sector_strength()`, `persist_regime_snapshot()` | add `subscribe_regime_change()` |
| `core/data/smart_money.py` | FII/DII + MF signals | none |
| `core/data/tickertape.py` | Sector, beta, MF holdings deltas | none |
| `core/data/news.py` | News + sentiment fetch | none |
| `core/data/universe.py` | Universe loader (swing default) | add second loader for accum universe |
| `core/data/fundamentals.py` (NEW) | yfinance P/E, D/E, EPS growth | full module — see 04 for spec |
| `core/db/base.py` | `Base`, `SessionLocal`, `engine`, `init_db()` | none |
| `core/db/models/shared.py` | `WeeklyRun`, `TradingParam`, `MockPortfolio`, `PaperTrade`, `Alert`, `MarketRegimeSnapshot` | extend `AlertType` enum (see below) |
| `core/db/models/swing.py` | `Recommendation`, `RejectedHeadline` | none |
| `core/db/models/accumulation.py` (NEW) | 4 accumulation tables | full module — see 04 |
| `core/alerts/channels.py` | `BaseChannel`, `TelegramChannel`, `WhatsAppChannel` stub | none |
| `core/alerts/monitor.py` | Generic loop with registered domain checkers | refactor — see 02.3 |

## Tasks

### 02.1 — Pin core public surface

Create `src/plutus/core/__init__.py` and re-export the public surface domain modules will use:

```python
from plutus.core.config import settings, get_settings
from plutus.core.config_params import get_params, set_param

from plutus.core.db.base import Base, SessionLocal, engine, init_db

from plutus.core.data.ohlcv import fetch_ohlcv, load_ohlcv, save_ohlcv
from plutus.core.data.regime import (
    get_nifty_regime,
    get_sector_strength,
    persist_regime_snapshot,
)
from plutus.core.data.universe import get_universe
from plutus.core.data.smart_money import get_fii_dii_flow, get_mf_signal
from plutus.core.data.tickertape import get_sector, get_beta, get_mf_holdings_delta

from plutus.core.alerts.channels import TelegramChannel
from plutus.core.alerts.monitor import (
    register_position_checker,
    run_monitor,
)
```

Domain code imports only from `plutus.core` (the package), not from sub-paths. This is the contract.

Test:

```python
# tests/core/test_public_surface.py
def test_public_surface_is_importable():
    from plutus import core
    expected = {
        "settings", "get_settings", "get_params", "set_param",
        "Base", "SessionLocal", "engine", "init_db",
        "fetch_ohlcv", "load_ohlcv", "save_ohlcv",
        "get_nifty_regime", "get_sector_strength", "persist_regime_snapshot",
        "get_universe",
        "get_fii_dii_flow", "get_mf_signal",
        "get_sector", "get_beta", "get_mf_holdings_delta",
        "TelegramChannel",
        "register_position_checker", "run_monitor",
    }
    for name in expected:
        assert hasattr(core, name), f"plutus.core missing {name}"
```

Acceptance: `pytest tests/core/test_public_surface.py -q` passes.

### 02.2 — AlertType enum extension

In `core/db/models/shared.py`, extend the existing `AlertType` enum:

```python
class AlertType(str, Enum):
    # existing swing alerts (do not rename)
    PRE_SL_WARNING       = "PRE_SL_WARNING"
    TARGET1_HIT          = "TARGET1_HIT"
    TARGET2_HIT          = "TARGET2_HIT"
    TREND_INVALIDATED    = "TREND_INVALIDATED"
    # new accumulation alerts
    TRANCHE2_TRIGGER     = "TRANCHE2_TRIGGER"
    TRANCHE3_TRIGGER     = "TRANCHE3_TRIGGER"
    BULL_READY           = "BULL_READY"
```

Add migration `NNN_extend_alert_type.sql` (where `NNN` is the next number):

```sql
-- SQLite stores enums as strings; no schema change needed.
-- For PostgreSQL targets:
ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'TRANCHE2_TRIGGER';
ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'TRANCHE3_TRIGGER';
ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'BULL_READY';
```

Test:

```python
# tests/core/test_models_shared.py::test_alert_type_extensions
from plutus.core.db.models import AlertType
def test_alert_type_has_accumulation_alerts():
    assert AlertType.TRANCHE2_TRIGGER.value == "TRANCHE2_TRIGGER"
    assert AlertType.TRANCHE3_TRIGGER.value == "TRANCHE3_TRIGGER"
    assert AlertType.BULL_READY.value == "BULL_READY"

def test_alert_type_preserves_swing_alerts():
    assert AlertType.PRE_SL_WARNING.value == "PRE_SL_WARNING"
    assert AlertType.TARGET1_HIT.value == "TARGET1_HIT"
```

Acceptance: both tests pass.

### 02.3 — Refactor `core/alerts/monitor.py` to registry pattern

Today, `monitor.check_open_positions()` directly contains the swing position checks. After this restructure, swing and accumulation each own their checker.

New shape in `core/alerts/monitor.py`:

```python
from typing import Callable, Protocol
from sqlalchemy.orm import Session

class PositionChecker(Protocol):
    def __call__(self, db: Session, channels: list) -> int:
        """Return number of alerts fired."""
        ...

_REGISTERED_CHECKERS: list[PositionChecker] = []

def register_position_checker(fn: PositionChecker) -> None:
    """Domain modules call this at import time to register their alert logic."""
    if fn not in _REGISTERED_CHECKERS:
        _REGISTERED_CHECKERS.append(fn)

def run_monitor(channels: list | None = None) -> dict:
    """Called by the scheduler every 15 min during NSE hours.

    Returns:
        dict: {"checkers_run": int, "alerts_fired": int}
    """
    channels = channels or get_active_channels()
    fired = 0
    with SessionLocal() as db:
        for checker in _REGISTERED_CHECKERS:
            fired += checker(db, channels)
    return {"checkers_run": len(_REGISTERED_CHECKERS), "alerts_fired": fired}
```

Existing swing logic moves to `swing/triggers.py`:

```python
from plutus.core.alerts.monitor import register_position_checker

def check_swing_positions(db, channels) -> int:
    # existing checks from monitor.check_open_positions
    ...

register_position_checker(check_swing_positions)
```

Importing `plutus.swing` triggers registration. Same pattern will be used by `plutus.accumulation.triggers`.

Tests:

```python
# tests/core/test_alerts_monitor.py
def test_register_position_checker_idempotent():
    from plutus.core.alerts.monitor import (
        register_position_checker, _REGISTERED_CHECKERS,
    )
    _REGISTERED_CHECKERS.clear()
    def fn(db, channels): return 0
    register_position_checker(fn)
    register_position_checker(fn)
    assert _REGISTERED_CHECKERS.count(fn) == 1

def test_run_monitor_calls_all_checkers(monkeypatch):
    from plutus.core.alerts import monitor as m
    m._REGISTERED_CHECKERS.clear()
    calls = []
    m.register_position_checker(lambda db, ch: (calls.append("a"), 2)[1])
    m.register_position_checker(lambda db, ch: (calls.append("b"), 1)[1])
    monkeypatch.setattr(m, "SessionLocal", _fake_session_factory())
    result = m.run_monitor(channels=[])
    assert result == {"checkers_run": 2, "alerts_fired": 3}
    assert calls == ["a", "b"]
```

Acceptance: both tests pass. The swing-side test in `tests/swing/test_triggers.py` (added in phase 03) confirms swing still fires alerts end-to-end after the refactor.

### 02.4 — Regime change subscription hook

Add to `core/data/regime.py` a thin pub-sub for regime flips. Used by accumulation's bull-ready alert (see 04).

```python
_REGIME_SUBSCRIBERS: list[Callable[[str, str], None]] = []

def subscribe_regime_change(fn: Callable[[str, str], None]) -> None:
    """fn(prev_trend, new_trend) is called when persist_regime_snapshot detects a flip."""
    if fn not in _REGIME_SUBSCRIBERS:
        _REGIME_SUBSCRIBERS.append(fn)

def _notify_regime_change(prev_trend: str, new_trend: str) -> None:
    for fn in _REGIME_SUBSCRIBERS:
        try:
            fn(prev_trend, new_trend)
        except Exception as exc:
            logger.exception("regime subscriber failed", subscriber=fn.__name__, exc=str(exc))
```

In existing `persist_regime_snapshot()`:

```python
def persist_regime_snapshot(db_session, snapshot_date=None):
    ...
    existing = db.query(MarketRegimeSnapshot)...  # current latest, before this write
    prev_trend = existing.nifty_trend if existing else None
    new_snapshot = MarketRegimeSnapshot(...)
    db.add(new_snapshot); db.commit()
    if prev_trend and prev_trend != new_snapshot.nifty_trend:
        _notify_regime_change(prev_trend, new_snapshot.nifty_trend)
```

Tests:

```python
# tests/core/data/test_regime_subscription.py
def test_subscribe_regime_change_fires_on_flip(in_memory_db):
    from plutus.core.data import regime
    received = []
    regime.subscribe_regime_change(lambda p, n: received.append((p, n)))
    _insert_regime_snapshot(in_memory_db, trend="BEAR")
    regime.persist_regime_snapshot(in_memory_db, _fake_now())  # writes BULL
    assert received == [("BEAR", "BULL")]

def test_subscribe_no_fire_when_unchanged(in_memory_db):
    received = []
    regime.subscribe_regime_change(lambda p, n: received.append((p, n)))
    _insert_regime_snapshot(in_memory_db, trend="BEAR")
    regime.persist_regime_snapshot(in_memory_db, _fake_now_writes_bear())
    assert received == []
```

Acceptance: both tests pass. No regression in the existing `test_regime/` suite.

### 02.5 — Universe loader takes a `kind` argument

Today `get_universe()` returns the swing universe (`seed_universe.csv` → filters). We need it to load either the swing universe or the accumulation universe.

```python
# core/data/universe.py
def get_universe(kind: str = "swing") -> list[str]:
    """Return list of NSE symbols.

    Args:
        kind: 'swing' (default — filtered momentum universe) or
              'accumulation' (Nifty 100 curated list for the accumulation screener).

    The 'accumulation' branch loads from core/data/seeds/nifty100_accumulation.csv.
    No filtering is applied — the curated list is the universe.
    """
```

Backwards-compatible: existing call sites that pass no argument keep getting the swing universe.

Tests:

```python
# tests/core/data/test_universe.py
def test_get_universe_default_is_swing():
    assert get_universe() == get_universe(kind="swing")

def test_get_universe_accumulation_returns_nifty100(tmp_path, monkeypatch):
    _stub_accumulation_csv(["HDFCBANK", "TCS", "INFY"])
    syms = get_universe(kind="accumulation")
    assert syms == ["HDFCBANK", "TCS", "INFY"]

def test_get_universe_unknown_kind_raises():
    with pytest.raises(ValueError, match="kind must be 'swing' or 'accumulation'"):
        get_universe(kind="banana")
```

The CSV `core/data/seeds/nifty100_accumulation.csv` is created in phase 04 with one symbol per line, header `symbol`. Until then, this test uses a stub.

Acceptance: 3 tests pass.

## Verification gate for phase 02

- [ ] `tests/core/test_public_surface.py` passes.
- [ ] `tests/core/test_models_shared.py::test_alert_type_*` pass.
- [ ] `tests/core/test_alerts_monitor.py` passes (2 tests).
- [ ] `tests/core/data/test_regime_subscription.py` passes (2 tests).
- [ ] `tests/core/data/test_universe.py::test_get_universe_*` passes (3 tests).
- [ ] All pre-existing tests still pass (`pytest -q` count unchanged from phase 01 exit).
- [ ] Domain isolation lint: `grep -rn "from plutus.swing\|from plutus.accumulation" src/plutus/core/` returns 0 lines.

Do not start phase 03 until every box is checked.
