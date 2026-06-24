from __future__ import annotations

from datetime import date

import pandas as pd

from plutus.data.fii_dii import fetch_flows, rolling_net_flow_5d


class _StubFlows:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def fetch(self, start: date, end: date) -> pd.DataFrame:
        return self._df.copy()


def _provider() -> _StubFlows:
    idx = pd.date_range("2025-01-01", periods=6, freq="D")
    # values in ₹ crore; FII net positive, DII mixed
    df = pd.DataFrame(
        {
            "fii_net_inr_crore": [100.0, -50.0, 200.0, 30.0, 10.0, -20.0],
            "dii_net_inr_crore": [-40.0, 60.0, -10.0, 5.0, 15.0, 25.0],
        },
        index=idx,
    )
    return _StubFlows(df)


def test_flow_signs_preserved() -> None:
    df = fetch_flows(date(2025, 1, 1), date(2025, 1, 6), _provider())
    assert df["fii_net_inr_crore"].iloc[0] > 0
    assert df["fii_net_inr_crore"].iloc[1] < 0
    assert df["dii_net_inr_crore"].iloc[0] < 0


def test_columns_in_crore_units() -> None:
    df = fetch_flows(date(2025, 1, 1), date(2025, 1, 6), _provider())
    assert "fii_net_inr_crore" in df.columns
    assert "dii_net_inr_crore" in df.columns


def test_5d_rolling_sum_matches_manual() -> None:
    df = fetch_flows(date(2025, 1, 1), date(2025, 1, 6), _provider())
    fii_5d = rolling_net_flow_5d(df["fii_net_inr_crore"])
    # last 5 fii values: -50 + 200 + 30 + 10 - 20 = 170
    assert fii_5d.iloc[-1] == 170.0
