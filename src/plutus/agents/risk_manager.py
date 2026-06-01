# plutus/agents/risk_manager.py
from __future__ import annotations

import json

from plutus.agents.openrouter_client import call_llm
from plutus.agents.prompts import RISK_MANAGER_PROMPT
from plutus.config import settings


def run_risk_management(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    target: float,
) -> dict:
    """Call the risk manager LLM. Pre-computes a sizing suggestion to anchor the LLM."""
    risk_per_share = abs(entry_price - stop_loss)
    max_loss = settings.INITIAL_CAPITAL * (settings.MAX_RISK_PCT / 100)
    shares_by_risk = int(max_loss / risk_per_share) if risk_per_share > 0 else 0
    shares_by_capital = int((settings.INITIAL_CAPITAL * 0.30) / entry_price) if entry_price > 0 else 0
    shares = max(0, min(shares_by_risk, shares_by_capital))

    user_msg = f"""Stock: {symbol}
Entry: ₹{entry_price:.2f}
Stop Loss: ₹{stop_loss:.2f}
Target: ₹{target:.2f}
Risk per share: ₹{risk_per_share:.2f}
Computed shares (by risk cap): {shares_by_risk}
Computed shares (by 30% capital cap): {shares_by_capital}
Final shares (suggested): {shares}
Capital required: ₹{shares * entry_price:,.0f}

Validate sizing. Capital pool: ₹{settings.INITIAL_CAPITAL:,.0f}.
Max risk per trade: ₹{max_loss:,.0f} ({settings.MAX_RISK_PCT}%)."""

    response = call_llm(
        messages=[
            {"role": "system", "content": RISK_MANAGER_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=settings.DEEPSEEK_FAST_MODEL,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(response)
