from __future__ import annotations

from datetime import date, timedelta

from plutus.backtesting.walk_forward import WalkForward, Window
from plutus.shared.types import BacktestTrade


def _wf() -> WalkForward:
    return WalkForward()


def test_windows_train_then_oos_no_overlap() -> None:
    wf = _wf()
    start = date(2020, 1, 1)
    end = date(2021, 1, 1)
    pairs = list(wf.windows(start, end, train_days=180, oos_days=30, step_days=30))
    assert pairs, "expected at least one window pair"
    for train, oos in pairs:
        # OOS strictly after train: oos.start >= train.end, no overlap.
        assert oos.start >= train.end
        assert train.start < train.end
        assert oos.start < oos.end


def test_windows_oos_strictly_after_train() -> None:
    wf = _wf()
    pairs = list(wf.windows(date(2020, 1, 1), date(2020, 12, 1)))
    for train, oos in pairs:
        assert oos.start >= train.end


def test_windows_slide_by_step_days() -> None:
    wf = _wf()
    pairs = list(
        wf.windows(
            date(2020, 1, 1),
            date(2021, 6, 1),
            train_days=180,
            oos_days=30,
            step_days=30,
        )
    )
    # consecutive train starts differ by step_days
    starts = [t.start for t, _ in pairs]
    for prev, cur in zip(starts, starts[1:], strict=False):
        assert (cur - prev) == timedelta(days=30)


def test_windows_stop_before_oos_exceeds_end() -> None:
    wf = _wf()
    end = date(2020, 9, 1)
    pairs = list(wf.windows(date(2020, 1, 1), end, train_days=180, oos_days=30, step_days=30))
    for _, oos in pairs:
        assert oos.end <= end


def test_stats_filters_trades_within_window() -> None:
    wf = _wf()
    window = Window(start=date(2020, 1, 1), end=date(2020, 2, 1))
    inside = BacktestTrade(
        symbol="A",
        bundle="trend",
        regime="BULL",
        entry_date=date(2020, 1, 10),
        exit_date=date(2020, 1, 20),
        realized_R=1.0,
        hold_days=10,
    )
    outside = BacktestTrade(
        symbol="B",
        bundle="trend",
        regime="BULL",
        entry_date=date(2020, 3, 1),
        exit_date=date(2020, 3, 10),
        realized_R=-1.0,
        hold_days=9,
    )
    stats = wf.stats([inside, outside], window)
    assert stats.n_trades == 1
    assert stats.expectancy_R == 1.0
