# plutus/agents/sentiment.py
from __future__ import annotations

import json

from plutus.agents.openrouter_client import call_llm, _parse_llm_json
from plutus.agents.prompts import SENTIMENT_ANALYST_PROMPT
from plutus.config import settings


def run_sentiment_analysis(
    symbol: str,
    news: list,
    news_classification: dict,
    reddit: dict,
) -> dict:
    """Call the sentiment analyst LLM. Returns the parsed JSON dict."""
    news_text = "\n".join(f"- {n['headline']} ({n['source']})" for n in news[:15]) or "No headlines."
    classification_text = json.dumps(news_classification, indent=2) if news_classification else "{}"
    reddit_text = (
        f"Reddit mentions: {reddit.get('mentions', 0)}, "
        f"sentiment: {reddit.get('sentiment', 'no_data')}, "
        f"avg upvote ratio: {reddit.get('avg_upvote_ratio', 'N/A')}"
    )
    user_msg = f"""Stock: {symbol}

Recent News (last 48h, post-prefilter):
{news_text}

Pre-classified news summary (from data.news.classify_news):
{classification_text}

Reddit Signal (last 7d):
{reddit_text}

Classify overall sentiment and identify any material events."""

    response = call_llm(
        messages=[
            {"role": "system", "content": SENTIMENT_ANALYST_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=settings.DEEPSEEK_FAST_MODEL,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return _parse_llm_json(response)
