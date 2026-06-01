# plutus/agents/smart_money.py
from __future__ import annotations

import json

from plutus.agents.openrouter_client import call_llm
from plutus.agents.prompts import SMART_MONEY_PROMPT
from plutus.config import settings


def run_smart_money_analysis(symbol: str, mf_data: dict, fii_data: dict) -> dict:
    """Call the smart-money analyst LLM. Returns the parsed JSON dict."""
    user_msg = f"""Stock: {symbol}

Mutual Fund Data (last 2 months):
{json.dumps(mf_data, indent=2)}

FII / DII Flow (today, NSE):
{json.dumps(fii_data, indent=2)}

Interpret institutional activity for this stock."""

    response = call_llm(
        messages=[
            {"role": "system", "content": SMART_MONEY_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=settings.DEEPSEEK_FAST_MODEL,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(response)
