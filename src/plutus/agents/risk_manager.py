# plutus/agents/risk_manager.py
from __future__ import annotations

from plutus.agents.openrouter_client import call_llm, _parse_llm_json
from plutus.agents.prompts import build_risk_manager_prompt
from plutus.config_params import get_params


def run_risk_management(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    target: float,
) -> dict:
    """Call the risk manager LLM. Pre-computes a sizing suggestion to anchor the LLM."""
    params = get_params()
    capital = params["initial_capital"]
    max_risk_pct = params["max_risk_pct_per_trade"]
    max_pct_capital = params["max_pct_capital_per_trade"]

    risk_per_share = abs(entry_price - stop_loss)
    max_loss = capital * (max_risk_pct / 100)
    shares_by_risk = int(max_loss / risk_per_share) if risk_per_share > 0 else 0
    shares_by_capital = int((capital * max_pct_capital / 100) / entry_price) if entry_price > 0 else 0
    shares = max(0, min(shares_by_risk, shares_by_capital))

    user_msg = f"""Stock: {symbol}
Entry: ₹{entry_price:.2f}
Stop Loss: ₹{stop_loss:.2f}
Target: ₹{target:.2f}
Risk per share: ₹{risk_per_share:.2f}
Computed shares (by risk cap): {shares_by_risk}
Computed shares (by {max_pct_capital:.0f}% capital cap): {shares_by_capital}
Final shares (suggested): {shares}
Capital required: ₹{shares * entry_price:,.0f}

Validate sizing. Capital pool: ₹{capital:,.0f}.
Max risk per trade: ₹{max_loss:,.0f} ({max_risk_pct}%)."""

    response = call_llm(
        messages=[
            {"role": "system", "content": build_risk_manager_prompt(params)},
            {"role": "user", "content": user_msg},
        ],
        model="deepseek/deepseek-v4-flash",
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return _parse_llm_json(response)
