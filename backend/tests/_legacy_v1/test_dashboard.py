"""Tests for dashboard rendering helpers and AppTest smoke test."""

import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from plutus.dashboard.helpers import drop_empty_revalidation as _drop_empty_revalidation


# ── Unit tests for _drop_empty_revalidation ────────────────────────────────


class TestDropEmptyRevalidation:
    def _df(self, revalidation_values):
        return pd.DataFrame(
            {
                "Symbol": ["A"] * len(revalidation_values),
                "Signal": ["BUY"] * len(revalidation_values),
                "Revalidation": revalidation_values,
            }
        )

    def test_all_empty_strings_drops_column(self):
        result = _drop_empty_revalidation(self._df(["", "", ""]))
        assert "Revalidation" not in result.columns

    def test_some_values_keeps_column(self):
        result = _drop_empty_revalidation(self._df(["", "check momentum", ""]))
        assert "Revalidation" in result.columns

    def test_empty_dataframe_drops_column(self):
        df = self._df([]).astype({"Revalidation": str})
        assert "Revalidation" not in _drop_empty_revalidation(df).columns

    def test_no_revalidation_column_is_noop(self):
        df = pd.DataFrame({"Symbol": ["A"], "Signal": ["BUY"]})
        assert list(_drop_empty_revalidation(df).columns) == ["Symbol", "Signal"]

    def test_filter_empties_df_then_drops_column(self):
        """Regression: signal_filter removes all rows → KeyError must not occur."""
        df = self._df(["", ""])
        df = df[df["Signal"] == "AVOID"]  # -> empty
        assert "Revalidation" not in _drop_empty_revalidation(df).columns

    def test_all_non_empty_keeps_column(self):
        result = _drop_empty_revalidation(self._df(["watch RSI", "check volume"]))
        assert "Revalidation" in result.columns


# ── AppTest smoke test ──────────────────────────────────────────────────────


class TestDashboardAppTest:
    def test_app_loads_without_crash(self):
        """Smoke: dashboard renders all tabs without unhandled exceptions (empty DB)."""
        from streamlit.testing.v1 import AppTest

        app_path = os.path.join(os.path.dirname(__file__), "..", "src", "dashboard.py")

        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            []
        )
        mock_db.query.return_value.all.return_value = []

        with patch("plutus.db.session.SessionLocal", return_value=mock_db):
            at = AppTest.from_file(app_path, default_timeout=30)
            at.run()

        assert not at.exception, f"Dashboard raised: {at.exception}"
