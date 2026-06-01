# plutus/agents/technical.py
from __future__ import annotations

import json

from plutus.agents.openrouter_client import call_llm
from plutus.agents.prompts import TECHNICAL_ANALYST_PROMPT
from plutus.config import settings


def run_technical_analysis(symbol: str, indicators: dict, backtest_results: dict) -> dict:
    """Call the technical analyst LLM. Returns the parsed JSON dict."""
    backtest_summary = "\n".join(
        f"  {name}: win_rate={r['win_rate']:.1%}, sharpe={r['sharpe']:.2f}, signal={r['signal']}"
        for name, r in backtest_results.items()
    )
    user_msg = f"""Stock: {symbol}

Current Indicators:
{json.dumps(indicators, indent=2)}

Backtest Results (last 90 days, 5 bundles):
{backtest_summary}

Analyse this setup and provide your technical verdict."""

    response = call_llm(
        messages=[
            {"role": "system", "content": TECHNICAL_ANALYST_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=settings.DEEPSEEK_FAST_MODEL,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(response)
