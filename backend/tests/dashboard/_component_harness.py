from __future__ import annotations

import streamlit as st

from plutus.dashboard.components.benchmarks_strip import benchmarks_strip
from plutus.dashboard.components.calibration_badge import calibration_badge
from plutus.dashboard.components.counterfactual import counterfactual
from plutus.dashboard.components.pillar_bar import pillar_bar
from plutus.dashboard.components.score_chip import score_chip
from plutus.dashboard.components.tranche_pills import tranche_pills
from plutus.shared.benchmarks.strip import BenchmarkResult

# Harness app exercised by tests/dashboard via AppTest. Renders every component once.

PILLARS = [
    ("Technical", 24, 30, "technical"),
    ("Expectancy", 20, 25, "expectancy"),
    ("Flow", 11, 15, "flow"),
    ("Sentiment", 4, 5, "sentiment"),
    ("Regime fit", 12, 15, "regime_fit"),
    ("Fundamentals", 7, 10, "fundamentals"),
]

st.title("component harness")

for label, value, max_value, token in PILLARS:
    pillar_bar(label, value, max_value, token)

calibration_badge(84, "high")
counterfactual("upgrades to BUY if entry < ₹420 or delivery > 50%")
score_chip("BUY", 76)
tranche_pills([1, 2, 3], total=5)
benchmarks_strip(
    BenchmarkResult(
        plutus_net_pct=3.2,
        nifty_net_pct=1.1,
        regime_switched_net_pct=0.8,
        random_liquid_net_pct=-0.4,
        plutus_profit_factor=1.8,
        plutus_n_trades=12,
    )
)
