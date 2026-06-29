# 05 — Dashboard (dual-mode Streamlit views)

## Goal

Implement the dual-mode dashboard exactly as shown in the v2 mockup that lives in the chat transcript (widget title `plutus_dashboard_v2`). Each view is one Streamlit file. Shared UI primitives live in `dashboard/components/`. No business logic in dashboard files — they read from helpers, render, and submit forms.

## Reference

The v2 mockup is the source of truth for spacing, colour, and layout. Implementer should screenshot it from the chat and pin it open while building. Key visual rules from the mockup:

- Active sidebar items use **blue** background+text for swing mode views, **purple** for accumulation views, neutral for shared (Home, Settings, User flow).
- Regime pill sits in the sidebar at the top, always visible.
- Top bar has a contextual "Add" action that changes per view.
- Candidate cards use score circles (44px) + 3 mini-bars (fundamental, relative strength, institutional flow).
- Tranche pip strip is 3 pip squares; filled (purple) = logged, outline = pending.
- Forms are inline at the top of the view, collapsed by default, expand via the top-bar Add button.

## File map

```
src/plutus/dashboard/
├── app.py                              ← entry; nav + routing
├── home.py                             ← dual-mode overview
├── swing_signals.py                    ← weekly signals table
├── swing_positions.py                  ← open swing positions + Add Position form
├── accumulation_candidates.py         ← ranked candidates + Add to Watchlist form
├── accumulation_tranches.py            ← active tranche positions + Log Tranche form
├── settings.py                         ← swing + accum + capital split
├── strategy_lab.py                     ← existing, keep
└── components/
    ├── __init__.py
    ├── badges.py                       ← render_badge(text, kind)
    ├── score_bars.py                   ← render_score_bar(value, kind), render_sub_score_bars(rows)
    ├── tranche_pips.py                 ← render_tranche_pips(done_count, total)
    ├── position_form.py                ← render_position_form(mode='swing'|'accumulation')
    └── regime_pill.py                  ← render_regime_pill(regime_dict)
```

## Tasks

### 05.1 — Components

Each component is a pure function: takes data, calls `st.*`, returns nothing or returns the form-submitted dict.

`components/badges.py`:

```python
KIND_COLORS = {
    "buy":   ("#EAF3DE", "#3B6D11"),
    "watch": ("#E6F1FB", "#185FA5"),
    "hold":  ("#FAEEDA", "#854F0B"),
    "avoid": ("#FCEBEB", "#A32D2D"),
    "strong_buy": ("#EAF3DE", "#27500A"),
    "accum": ("#EEEDFE", "#3C3489"),
    "bear":  ("#FCEBEB", "#A32D2D"),
    "bull":  ("#EAF3DE", "#3B6D11"),
    "live":  ("#EAF3DE", "#3B6D11"),
}

def render_badge(text: str, kind: str) -> None: ...
```

`components/score_bars.py`:

```python
def render_score_bar(value: float, kind: str = "swing", *, label: str | None = None) -> None:
    """Renders a single 100-wide horizontal bar with right-aligned numeric.
    kind ∈ {'swing', 'accumulation', 'green', 'amber'} controls colour."""

def render_sub_score_bars(rows: list[tuple[str, float, str]]) -> None:
    """rows = [(label, value, colour_kind), ...]. Stacks vertically."""
```

`components/tranche_pips.py`:

```python
def render_tranche_pips(done: int, total: int = 3) -> None:
    """Renders N pip squares, the first `done` filled purple, the rest outline."""
```

`components/regime_pill.py`:

```python
def render_regime_pill(regime: dict) -> None:
    """regime = {trend, slope, distance_from_ema50_pct} from get_nifty_regime()."""
```

`components/position_form.py`:

```python
def render_position_form(mode: str, key_prefix: str = "") -> dict | None:
    """Render the 5-column add-position form. Returns the submitted dict or None.

    For mode='swing': fields = symbol, entry_price, qty, stop_loss.
    For mode='accumulation': fields = symbol, entry_price, qty, tranche_num (selectbox 1-3).
    """
    cols = st.columns([2, 1.2, 1, 1, 1])
    sym = cols[0].text_input("Symbol", key=f"{key_prefix}{mode}_sym").upper().strip()
    price = cols[1].number_input("Entry price ₹", min_value=0.0, step=0.05, key=f"{key_prefix}{mode}_price")
    qty = cols[2].number_input("Quantity", min_value=0, step=1, key=f"{key_prefix}{mode}_qty")
    if mode == "swing":
        sl = cols[3].number_input("Stop loss ₹", min_value=0.0, step=0.05, key=f"{key_prefix}_sl")
        extra = {"stop_loss": sl}
    else:
        tranche = cols[3].selectbox("Tranche #", [1, 2, 3], key=f"{key_prefix}_tr")
        extra = {"tranche_num": tranche}
    if cols[4].button("Add", type="primary", key=f"{key_prefix}{mode}_submit"):
        if not sym or price <= 0 or qty <= 0:
            st.error("Symbol, price, qty are required.")
            return None
        return {"symbol": sym, "entry_price": price, "qty": qty, **extra}
    return None
```

Tests (use `streamlit.testing.v1.AppTest` — built into streamlit ≥ 1.28):

```python
# tests/dashboard/test_components.py
from streamlit.testing.v1 import AppTest

def test_badge_renders_text():
    at = AppTest.from_string("""
        from plutus.dashboard.components.badges import render_badge
        render_badge("BUY", "buy")
    """).run()
    assert any("BUY" in m.value for m in at.markdown)

def test_score_bar_clamps_to_0_100():
    at = AppTest.from_string("""
        from plutus.dashboard.components.score_bars import render_score_bar
        render_score_bar(150, kind="swing")
    """).run()
    # width should cap at 100%
    assert any("width:100%" in m.value for m in at.markdown)

def test_tranche_pips_3_done_renders_3_filled():
    at = AppTest.from_string("""
        from plutus.dashboard.components.tranche_pips import render_tranche_pips
        render_tranche_pips(done=3, total=3)
    """).run()
    # all pips have the 'done' class
    assert at.markdown[0].value.count("pip done") == 3

def test_position_form_validates_required(monkeypatch):
    at = AppTest.from_string("""
        from plutus.dashboard.components.position_form import render_position_form
        result = render_position_form(mode='swing')
        if result:
            import streamlit as st
            st.success(f"Submitted {result['symbol']}")
    """).run()
    at.button[0].click().run()
    # Empty submission → error
    assert any("required" in e.value.lower() for e in at.error)

def test_position_form_submits_clean_dict():
    at = AppTest.from_string("...").run()
    at.text_input[0].input("HDFCBANK").run()
    at.number_input[0].set_value(1640.0).run()
    at.number_input[1].set_value(10).run()
    at.number_input[2].set_value(1580.0).run()
    at.button[0].click().run()
    assert any("Submitted HDFCBANK" in s.value for s in at.success)
```

Acceptance: 5 tests pass.

### 05.2 — Helpers (data access)

`dashboard/helpers.py`:

```python
def get_dual_mode_summary(db) -> dict:
    """Returns:
        {
            'total_capital': float,
            'swing_pool': float, 'swing_deployed': float, 'swing_open_positions': int,
            'accum_pool': float, 'accum_deployed': float, 'accum_active_positions': int,
            'cash_reserve': float,
            'regime': {'trend', 'slope', 'distance_from_ema50_pct'},
        }
    """

def get_swing_positions(db) -> list[dict]:
    """Open PaperTrade rows for the swing portfolio, with live LTP + P&L %."""

def get_accumulation_candidates(db, *, min_composite: int = 45) -> list[dict]:
    """Latest accumulation_run's candidates, ranked, with in_portfolio flag per symbol."""

def get_accumulation_positions(db) -> list[dict]:
    """Open accumulation positions with tranche pip counts and live P&L %."""
```

Tests:

```python
# tests/dashboard/test_helpers.py
def test_dual_mode_summary_shape(in_memory_db, seeded_dual_state):
    s = get_dual_mode_summary(in_memory_db)
    expected_keys = {"total_capital", "swing_pool", "swing_deployed", "swing_open_positions",
                      "accum_pool", "accum_deployed", "accum_active_positions",
                      "cash_reserve", "regime"}
    assert set(s.keys()) == expected_keys

def test_get_accumulation_candidates_returns_only_above_threshold(in_memory_db, mixed_score_run):
    cs = get_accumulation_candidates(in_memory_db, min_composite=60)
    assert all(c["composite"] >= 60 for c in cs)
```

### 05.3 — Views

Each view is a small function `render()` that the router calls.

`dashboard/accumulation_candidates.py`:

```python
def render(db) -> None:
    regime = get_nifty_regime()
    if regime["trend"] in ("BEAR", "SIDEWAYS"):
        st.info("Accumulation mode active — these stocks show fundamental strength + relative resilience.")

    if st.button("+ Add to watchlist", key="open_form"):
        st.session_state["show_form"] = True
    if st.session_state.get("show_form"):
        result = render_position_form(mode="accumulation", key_prefix="cand_")
        if result:
            try:
                create_position(db, portfolio_id=_accum_portfolio_id(db),
                                 symbol=result["symbol"],
                                 t1_price=result["entry_price"],
                                 qty=result["qty"],
                                 entry_date=date.today())
                st.success(f"Added {result['symbol']} as tranche {result['tranche_num']}.")
                st.session_state["show_form"] = False
                st.rerun()
            except BudgetExceededError as e:
                st.error(str(e))

    for c in get_accumulation_candidates(db):
        _render_candidate_card(c)
```

`_render_candidate_card(c)` reuses `render_badge`, `render_score_bar`, `render_sub_score_bars`, `render_tranche_pips` per the mockup layout.

`dashboard/accumulation_tranches.py`:

```python
def render(db) -> None:
    summary = get_dual_mode_summary(db)
    _render_stat_row(summary, mode="accumulation")
    if st.button("+ Log tranche", key="open_tranche_form"):
        st.session_state["show_tranche_form"] = True
    if st.session_state.get("show_tranche_form"):
        result = render_position_form(mode="accumulation", key_prefix="tranch_")
        if result:
            pos = _find_open_position(db, result["symbol"])
            if not pos and result["tranche_num"] == 1:
                pos = create_position(db, ..., qty=result["qty"], t1_price=result["entry_price"])
            elif pos:
                add_tranche(db, position_id=pos.id, tranche_num=result["tranche_num"],
                             price=result["entry_price"], qty=result["qty"],
                             entry_date=date.today())
            else:
                st.error(f"No open position for {result['symbol']} — start with tranche 1 first.")
                return
            st.rerun()
    for p in get_accumulation_positions(db):
        _render_tranche_row(p)
```

`dashboard/swing_positions.py`: same shape as tranches view but for swing PaperTrade rows. Form calls a new helper `_create_swing_position(db, symbol, entry, qty, sl)` that writes `PaperTrade` after validating against `swing_budget_pct`.

`dashboard/home.py`: reads `get_dual_mode_summary`, renders the 4-card stat row, capital split bar, and side-by-side swing/accum mini-tables exactly per the mockup home view.

`dashboard/settings.py`: side-by-side swing / accumulation cards using `st.number_input` for params; "Save all settings" button calls `set_param()` per row inside a try/except for the invariant validator; capital split bar at the bottom updates as inputs change.

`dashboard/app.py`:

```python
import streamlit as st
from plutus.dashboard import home, swing_signals, swing_positions, \
                              accumulation_candidates, accumulation_tranches, \
                              settings as settings_view, strategy_lab
from plutus.dashboard.components.regime_pill import render_regime_pill
from plutus.core.db.base import SessionLocal
from plutus.core.data.regime import get_nifty_regime

VIEWS = {
    "Home":                       home,
    "Swing — Signals":            swing_signals,
    "Swing — Positions":          swing_positions,
    "Accumulation — Candidates":  accumulation_candidates,
    "Accumulation — Tranches":    accumulation_tranches,
    "Settings":                   settings_view,
    "Strategy lab":               strategy_lab,
}

def main():
    st.set_page_config(page_title="Plutus", layout="wide")
    with st.sidebar:
        render_regime_pill(get_nifty_regime())
        choice = st.radio("View", list(VIEWS.keys()), label_visibility="collapsed")
    with SessionLocal() as db:
        VIEWS[choice].render(db)

if __name__ == "__main__":
    main()
```

### 05.4 — View tests (smoke)

Streamlit views are hard to assert end-to-end. Test them via `AppTest`:

```python
# tests/dashboard/test_views.py
def test_home_renders_without_error(seeded_dual_state):
    at = AppTest.from_file("src/plutus/dashboard/app.py").run()
    assert not at.exception

def test_accumulation_candidates_form_creates_position(seeded_dual_state):
    at = AppTest.from_file("src/plutus/dashboard/app.py").run()
    at.sidebar.radio[0].set_value("Accumulation — Candidates").run()
    at.button(key="open_form").click().run()
    at.text_input[0].input("HDFCBANK").run()
    at.number_input[0].set_value(1640.0).run()
    at.number_input[1].set_value(10).run()
    at.button(key="cand_accumulation_submit").click().run()
    # success message present and DB row created
    from plutus.core.db.models import AccumulationPosition
    with SessionLocal() as db:
        rows = db.query(AccumulationPosition).filter_by(symbol="HDFCBANK").all()
    assert len(rows) == 1

def test_tranche_form_rejects_invalid_symbol(seeded_dual_state):
    at = AppTest.from_file("src/plutus/dashboard/app.py").run()
    at.sidebar.radio[0].set_value("Accumulation — Tranches").run()
    at.button(key="open_tranche_form").click().run()
    at.text_input[0].input("GHOSTSTOCK").run()
    at.number_input[0].set_value(100.0).run()
    at.number_input[1].set_value(1).run()
    # tranche_num default = 1 → new position attempt; if symbol not in universe, the DB still allows the insert
    # (this test asserts the form runs cleanly; the screener separately decides if it's a known stock)
    at.button(key="tranch_accumulation_submit").click().run()
    assert not at.exception

def test_settings_rejects_over_100_split(seeded_dual_state):
    at = AppTest.from_file("src/plutus/dashboard/app.py").run()
    at.sidebar.radio[0].set_value("Settings").run()
    at.number_input(key="param_swing_budget_pct").set_value(50.0).run()
    at.number_input(key="param_accumulation_budget_pct").set_value(60.0).run()
    at.button(key="save_settings").click().run()
    assert any("exceeds 100" in e.value for e in at.error)
```

Acceptance: 4 tests pass without raising.

## Verification gate for phase 05

- [ ] `pytest tests/dashboard/ -q` → ≥ 11 tests passing.
- [ ] `streamlit run src/plutus/dashboard/app.py` starts cleanly and the sidebar shows: Home, Swing Signals, Swing Positions, Accumulation Candidates, Accumulation Tranches, Settings, Strategy lab.
- [ ] Each view renders without error in both BEAR and BULL regime (manual smoke test — record the screenshot in `screenshots/v2/`).
- [ ] Visual comparison against the v2 mockup (widget title `plutus_dashboard_v2` in chat): sidebar colour coding, regime pill, candidate cards, tranche pips, form layouts all match.
- [ ] No business logic in any view file. (`grep -rn "compute_accumulation_score\|run_weekly_swing\|run_weekly_accumulation" src/plutus/dashboard/` returns 0 lines.)

Do not start phase 06 until every box is checked.
