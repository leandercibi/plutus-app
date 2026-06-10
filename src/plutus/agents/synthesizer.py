# plutus/agents/synthesizer.py
from __future__ import annotations

import json
from dataclasses import asdict

from plutus.agents.openrouter_client import call_llm, _parse_llm_json
from plutus.agents.prompts import SYNTHESIZER_PROMPT
from plutus.agents.scoring import Classification, ScoreBreakdown
from plutus.config import settings


def run_synthesis(
    symbol: str,
    breakdown: ScoreBreakdown,
    classification: Classification,
    current_price: float = 0.0,
    technical_output: dict | None = None,
    sentiment_output: dict | None = None,
    smart_money_output: dict | None = None,
    risk_output: dict | None = None,
) -> dict:
    """
    Call the synthesizer LLM to write a narrative and risk flags.
    The recommendation/confidence are NOT determined here — they come from scoring.py.
    Returns: {"narrative": str, "top_3_risk_flags": list[str]}
    """
    inputs = {
        "symbol": symbol,
        "current_price": current_price,
        "recommendation": classification.value,
        "composite_score": breakdown.composite,
        "sub_scores": {
            "technical":   breakdown.technical,
            "smart_money": breakdown.smart_money,
            "sentiment":   breakdown.sentiment,
            "regime":      breakdown.regime,
            "rr":          breakdown.rr,
        },
        "hard_avoid_reasons": list(breakdown.hard_avoid_reasons),
        "technical_output":    technical_output or {},
        "sentiment_output":    sentiment_output or {},
        "smart_money_output":  smart_money_output or {},
        "risk_output":         risk_output or {},
    }

    user_msg = f"""Stock: {symbol} | Price: ₹{current_price:.2f}
Composite Score: {breakdown.composite}/100 → {classification.value}

Sub-scores: {json.dumps(inputs['sub_scores'], indent=2)}
Hard avoid reasons: {inputs['hard_avoid_reasons']}

Technical context:
{json.dumps(technical_output or {}, indent=2)}

Sentiment context:
{json.dumps(sentiment_output or {}, indent=2)}

Smart money context:
{json.dumps(smart_money_output or {}, indent=2)}

Write the narrative and top_3_risk_flags. Output JSON only."""

    response = call_llm(
        messages=[
            {"role": "system", "content": SYNTHESIZER_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=settings.DEEPSEEK_REASON_MODEL,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    parsed = _parse_llm_json(response)

    return {
        "narrative": parsed.get("narrative", ""),
        "top_3_risk_flags": parsed.get("top_3_risk_flags", [])[:3],
    }
