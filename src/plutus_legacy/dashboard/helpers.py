"""Pure DataFrame helpers for the dashboard — no Streamlit imports."""

from __future__ import annotations

import pandas as pd


def drop_empty_revalidation(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the Revalidation column if all values are empty (or df is empty)."""
    if "Revalidation" not in df.columns:
        return df
    if df.empty or not df["Revalidation"].any():
        return df.drop(columns=["Revalidation"])
    return df
