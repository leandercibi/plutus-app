# plutus/agents/synthesizer.py
from __future__ import annotations

import json

from plutus.agents.openrouter_client import call_llm
from plutus.agents.prompts import SYNTHESIZER_PROMPT
from plutus.config import settings


def run_synthesis(
    symbol: str,
    current_price: float,
    technical: dict,
    sentiment: dict,
    smart_money: dict,
    risk: dict,
) -> dict:
    """
    Call the synthesizer LLM (model env var DEEPSEEK_REASON_MODEL).
    Currently resolves to V4 Flash; user can swap to a heavier reasoner via env.
    """
    user_msg = f"""Stock: {symbol} | Current Price: ₹{current_price:.2f}

TECHNICAL ANALYSIS:
{json.dumps(technical, indent=2)}

SENTIMENT ANALYSIS:
{json.dumps(sentiment, indent=2)}

SMART MONEY SIGNALS:
{json.dumps(smart_money, indent=2)}

RISK ASSESSMENT:
{json.dumps(risk, indent=2)}

Produce the final investment recommendation. Remember:
- Output JSON only, matching the schema in the system prompt.
- entry_mid MUST equal (entry_zone[0] + entry_zone[1]) / 2.
- hold_days_min and hold_days_max are integers (not a string)."""

    response = call_llm(
        messages=[
            {"role": "system", "content": SYNTHESIZER_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=settings.DEEPSEEK_REASON_MODEL,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    parsed = json.loads(response)

    # Defensive: enforce entry_mid even if the LLM forgot.
    ez = parsed.get("entry_zone")
    if ez and len(ez) == 2 and parsed.get("entry_mid") is None:
        parsed["entry_mid"] = round((float(ez[0]) + float(ez[1])) / 2, 2)

    return parsed
