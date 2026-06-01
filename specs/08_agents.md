# 08 — LangGraph Agents (DeepSeek via OpenRouter)

---

## Architecture Overview

```
run_analysis("RELIANCE")
        │
        ▼
   LangGraph StateGraph
        │
        ▼
   fetch_data_node
        │
        ├──(parallel send)──► technical_node    ──┐
        ├──(parallel send)──► sentiment_node    ──┤
        ├──(parallel send)──► smart_money_node  ──┤
        │                                         ▼
        │                               risk_manager_node
        │                                         │
        └──────────────────────────────► synthesizer_node
                                                  │
                                          save_recommendation_node
                                                  │
                                            RecommendationDict
```

**Parallel nodes:** `technical_node`, `sentiment_node`, `smart_money_node` run simultaneously after `fetch_data_node`.
**Sequential nodes:** `risk_manager_node` fans-in after the three parallel nodes (it needs technical's stop/target prices). `synthesizer_node` runs last and produces the final verdict.
**Persistence:** `save_recommendation_node` writes to `recommendations` (see `04_database.md`).

---

## Agent → Model Mapping

All five LLM-driven nodes currently resolve to **DeepSeek V4 Flash** via OpenRouter. The synthesizer reads its model name from a separate env var (`DEEPSEEK_REASON_MODEL`) so the user can later swap in a heavier reasoner (e.g. `deepseek/deepseek-r1`) without touching code.

| Node | Model env var | Default value (`config.py`) |
|---|---|---|
| `technical_node` | `DEEPSEEK_FAST_MODEL` | `deepseek/deepseek-v4-flash` |
| `sentiment_node` | `DEEPSEEK_FAST_MODEL` | `deepseek/deepseek-v4-flash` |
| `smart_money_node` | `DEEPSEEK_FAST_MODEL` | `deepseek/deepseek-v4-flash` |
| `risk_manager_node` | `DEEPSEEK_FAST_MODEL` | `deepseek/deepseek-v4-flash` |
| `synthesizer_node` | `DEEPSEEK_REASON_MODEL` | `deepseek/deepseek-v4-flash` |

> **Heavier-reasoner swap:** set `DEEPSEEK_REASON_MODEL=deepseek/deepseek-r1` in `.env` and restart `plutus-main.service`. No other change needed.

---

## `plutus/agents/openrouter_client.py`

Simple OpenAI-compatible HTTP client to OpenRouter. One function: `call_llm`. Retries on HTTP 429 with exponential backoff (1 s, 2 s, 4 s, capped at 16 s). Other 5xx errors retry up to 2 times. 4xx errors (other than 429) raise immediately.

```python
# plutus/agents/openrouter_client.py
from __future__ import annotations

import time
from typing import Optional

import httpx
import structlog

from plutus.config import settings

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MAX_429_RETRIES = 5
_MAX_5XX_RETRIES = 2
_BASE_BACKOFF_SEC = 1.0
_MAX_BACKOFF_SEC = 16.0


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter returns a non-recoverable error."""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/plutus-trading",
        "X-Title": "Plutus Trading Engine",
    }


def call_llm(
    messages: list,
    model: str,
    response_format: Optional[dict] = None,
    temperature: float = 0.2,
) -> str:
    """
    Send a chat completion request to OpenRouter and return the assistant's
    text content. Retries on 429 (rate limit) with exponential backoff.

    Args:
        messages: list of {"role": ..., "content": ...} dicts.
        model: OpenRouter model identifier, e.g. "deepseek/deepseek-v4-flash".
        response_format: optional, e.g. {"type": "json_object"}.
        temperature: sampling temperature (default 0.2 — deterministic).

    Returns:
        The assistant message content as a string.
    """
    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    backoff = _BASE_BACKOFF_SEC
    attempts_429 = 0
    attempts_5xx = 0

    with httpx.Client(timeout=_TIMEOUT) as client:
        while True:
            try:
                resp = client.post(url, headers=_headers(), json=payload)
            except httpx.RequestError as e:
                if attempts_5xx >= _MAX_5XX_RETRIES:
                    raise OpenRouterError(f"network error: {e}") from e
                attempts_5xx += 1
                logger.warning("openrouter_network_retry", attempt=attempts_5xx, err=str(e))
                time.sleep(min(backoff, _MAX_BACKOFF_SEC))
                backoff *= 2
                continue

            if resp.status_code == 429:
                if attempts_429 >= _MAX_429_RETRIES:
                    raise OpenRouterError(
                        f"OpenRouter 429 after {attempts_429} retries"
                    )
                attempts_429 += 1
                wait = min(backoff, _MAX_BACKOFF_SEC)
                logger.warning("openrouter_rate_limited", attempt=attempts_429, sleep=wait)
                time.sleep(wait)
                backoff *= 2
                continue

            if 500 <= resp.status_code < 600:
                if attempts_5xx >= _MAX_5XX_RETRIES:
                    raise OpenRouterError(
                        f"OpenRouter {resp.status_code}: {resp.text[:200]}"
                    )
                attempts_5xx += 1
                wait = min(backoff, _MAX_BACKOFF_SEC)
                logger.warning("openrouter_5xx_retry", code=resp.status_code, attempt=attempts_5xx)
                time.sleep(wait)
                backoff *= 2
                continue

            if resp.status_code >= 400:
                raise OpenRouterError(
                    f"OpenRouter {resp.status_code}: {resp.text[:500]}"
                )

            data = resp.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                raise OpenRouterError(f"malformed response: {data}") from e

            usage = data.get("usage", {})
            logger.debug(
                "llm_call",
                model=model,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
            return content
```

---

## `plutus/agents/prompts.py` — All System Prompts

```python
# plutus/agents/prompts.py

TECHNICAL_ANALYST_PROMPT = """You are a senior technical analyst specialising in Indian equities (NSE/BSE).
You analyse quantitative indicator data and produce structured trading signals.

Your output MUST be a JSON object with this exact schema:
{
  "score": <float 0-10>,
  "verdict": <"BUY" | "SELL" | "HOLD" | "NEUTRAL">,
  "patterns_detected": [<list of pattern names as strings>],
  "entry_zone": [<float low>, <float high>],
  "target1": <float>,
  "target2": <float>,
  "stop_loss": <float>,
  "rr_ratio": <float>,
  "trend_direction": <"UP" | "DOWN" | "SIDEWAYS">,
  "market_regime": <"TRENDING" | "RANGING" | "VOLATILE">,
  "reasoning": <string, max 200 words>
}

Rules:
- Score 7+ = strong BUY signal
- Score 4-6 = HOLD/WATCH
- Score below 4 = avoid
- entry_zone: realistic entry range based on current price and nearest support
- Always compute R:R ratio. Reject any setup below 1.5 R:R
- Be specific: quote the actual values from the data
- Consider multi-timeframe context if provided"""


SENTIMENT_ANALYST_PROMPT = """You are a sentiment analyst specialising in Indian equity markets.
You classify news and social media sentiment for a given stock.

Your output MUST be a JSON object with this exact schema:
{
  "sentiment_score": <float -5 to +5>,
  "sentiment_label": <"strongly_positive" | "positive" | "neutral" | "negative" | "strongly_negative">,
  "is_material_event": <boolean>,
  "material_event_type": <string or null>,
  "summary": <string, 1-2 sentences>,
  "key_headlines": [<list of up to 3 most important headline strings>],
  "reddit_signal": <"bullish" | "bearish" | "neutral" | "no_data">
}

Material events that MUST set is_material_event=true:
- USFDA/regulatory action (import alert, warning letter, show cause)
- Promoter stake change > 1%
- Block/bulk deal > ₹50 Crore
- Earnings miss/beat > 10% vs estimates
- Rating downgrade/upgrade
- Acquisition, merger, takeover announcement
- Management change (CEO/CFO/MD)
- Default, insolvency, fraud, SEBI action
- Dividend, bonus, stock split announcement

Score +5 = overwhelmingly positive, 0 = neutral, -5 = overwhelmingly negative."""


SMART_MONEY_PROMPT = """You are an institutional flow analyst for Indian equity markets.
You interpret mutual fund holdings data and FII/DII flow data.

Your output MUST be a JSON object with this exact schema:
{
  "verdict": <"ACCUMULATING" | "REDUCING" | "NEUTRAL" | "UNKNOWN">,
  "confidence": <float 0-10>,
  "mf_count_accumulating": <int>,
  "mf_count_reducing": <int>,
  "fii_signal": <"net_buyer" | "net_seller" | "neutral" | "unknown">,
  "dii_signal": <"net_buyer" | "net_seller" | "neutral" | "unknown">,
  "institutional_bias": <"BULLISH" | "BEARISH" | "NEUTRAL">,
  "reasoning": <string, max 100 words>
}

ACCUMULATING = 2+ mutual funds increased holdings in last 2 months
REDUCING = 2+ mutual funds reduced holdings significantly
NEUTRAL = mixed or minimal change

FII + DII both buying same stock = strongest institutional signal."""


RISK_MANAGER_PROMPT = """You are a quantitative risk manager for a retail trader in India.
Capital: ₹1,00,000 INR. Max risk per trade: 5% (₹5,000). Max open positions: 4 advisory, 10 hard cap.

Given entry price, stop loss, and current portfolio state, compute optimal position sizing.

Your output MUST be a JSON object with this exact schema:
{
  "shares": <int>,
  "capital_used": <float>,
  "pct_of_capital": <float>,
  "max_loss_inr": <float>,
  "max_loss_pct": <float>,
  "rr_ratio": <float>,
  "verdict": <"ACCEPTABLE" | "REDUCE_SIZE" | "REJECT">,
  "rejection_reason": <string or null>,
  "adjusted_stop": <float or null>
}

REJECT conditions:
- R:R ratio < 1.5
- Max loss would exceed ₹5,000
- Already at hard cap of 10 open positions
- Capital usage > 30% of total capital in single trade
- Stock price would require fractional shares (result in 0 shares)

REDUCE_SIZE: suggest smaller position to fit within risk limits.
At 4+ open positions, set verdict=REDUCE_SIZE with note in rejection_reason (advisory)."""


SYNTHESIZER_PROMPT = """You are the chief investment analyst for a retail trader in India.
You receive analysis from 4 specialist agents and produce the FINAL recommendation.

Capital: ₹1,00,000 INR. Swing trading horizon: 3-10 days. Market: NSE India.

Your output MUST be a JSON object with this EXACT schema (note: hold_days is split into
two integer fields, and entry_mid must be computed as (entry_low + entry_high) / 2):

{
  "recommendation": <"BUY" | "SELL" | "HOLD" | "WATCH" | "AVOID">,
  "confidence": <float 0-10>,
  "entry_zone": [<float low>, <float high>],
  "entry_mid": <float>,                        // = (entry_zone[0] + entry_zone[1]) / 2
  "targets": [<float target1>, <float target2>],
  "stop_loss": <float>,
  "risk_reward": <float>,
  "position": {
    "shares": <int>,
    "capital": <float>,
    "pct_of_portfolio": <float>,
    "max_loss_inr": <float>
  },
  "hold_days_min": <int>,                      // e.g. 5
  "hold_days_max": <int>,                      // e.g. 8 (must be >= hold_days_min)
  "strategy": <string, which bundle(s) triggered this>,
  "risk_flags": [<list of risk warnings as strings>],
  "reasoning": <string, 150-250 words explaining the full thesis>
}

CRITICAL RULES:
- BUY only when technical score >= 6 AND sentiment >= 0 AND risk verdict = ACCEPTABLE
- AVOID when any of: material negative event, institutional reducing, stop < 2% away
- WATCH when signals are mixed but not strong enough to commit
- entry_mid MUST equal (entry_zone[0] + entry_zone[1]) / 2 to 2 decimal places
- hold_days_min and hold_days_max MUST both be integers in [3, 10] with min <= max
- reasoning must mention: technical basis, sentiment context, smart money signal
- Be specific: mention actual price levels, actual patterns detected"""


NEWS_CLASSIFIER_PROMPT = """You classify news headlines for Indian stocks.
Identify overall sentiment and detect material events.

Your output MUST be a JSON object with this exact schema:
{
  "sentiment_score": <int -5 to +5>,
  "sentiment_label": <"positive" | "negative" | "neutral">,
  "is_material": <boolean>,
  "material_event_type": <string or null>,
  "summary": <string, 1 sentence>
}

Material events (set is_material=true):
- Regulatory action (SEBI, USFDA, RBI, NCLT)
- Earnings beat/miss > 10%
- Promoter / block / bulk deal
- Rating change, default, insolvency
- M&A, acquisition, merger, demerger
- Management change at CEO/CFO/MD/Chairman level"""
```

---

## `plutus/agents/graph.py` — LangGraph StateGraph

```python
# plutus/agents/graph.py
from __future__ import annotations

import time
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from plutus.agents.risk_manager import run_risk_management
from plutus.agents.sentiment import run_sentiment_analysis
from plutus.agents.smart_money import run_smart_money_analysis
from plutus.agents.synthesizer import run_synthesis
from plutus.agents.technical import run_technical_analysis
from plutus.backtesting.runner import run_all_bundles
from plutus.data.news import classify_news, fetch_news
from plutus.data.ohlcv import add_indicators, fetch_ohlcv
from plutus.data.reddit import get_reddit_sentiment
from plutus.data.smart_money import get_fii_dii_flow, get_mf_signal
from plutus.db.models import Recommendation
from plutus.db.session import SessionLocal


class AnalysisState(TypedDict):
    # Input
    symbol: str
    exchange: str
    # Intermediate data (populated by fetch_data_node)
    ohlcv_json: str
    indicators: dict
    backtest_results: dict
    news_data: list
    news_classification: dict
    reddit_data: dict
    mf_data: dict
    fii_data: dict
    current_price: float
    # Agent outputs
    technical_output: dict
    sentiment_output: dict
    smart_money_output: dict
    risk_output: dict
    # Final
    recommendation: dict
    error: Optional[str]


# ── Nodes ────────────────────────────────────────────────────────────────────

def fetch_data_node(state: AnalysisState) -> dict:
    """Fetches all data needed by the parallel agent nodes."""
    symbol = state["symbol"]
    exchange = state.get("exchange", "NSE")

    df = fetch_ohlcv(symbol, days=90, exchange=exchange)
    df = add_indicators(df)
    current_price = float(df["Close"].iloc[-1])

    recent = df.tail(30)
    indicators = {
        "current_price": round(current_price, 2),
        "ema9": round(df["EMA_9"].iloc[-1], 2),
        "ema21": round(df["EMA_21"].iloc[-1], 2),
        "ema50": round(df["EMA_50"].iloc[-1], 2),
        "ema200": round(df["EMA_200"].iloc[-1], 2),
        "rsi": round(df["RSI_14"].iloc[-1], 2),
        "macd": round(df["MACD_12_26_9"].iloc[-1], 4),
        "macd_signal": round(df["MACDs_12_26_9"].iloc[-1], 4),
        "macd_hist": round(df["MACDh_12_26_9"].iloc[-1], 4),
        "bb_lower": round(df["BBL_20_2.0"].iloc[-1], 2),
        "bb_mid": round(df["BBM_20_2.0"].iloc[-1], 2),
        "bb_upper": round(df["BBU_20_2.0"].iloc[-1], 2),
        "atr": round(df["ATRr_14"].iloc[-1], 2),
        "adx": round(df["ADX_14"].iloc[-1], 2),
        "stoch_k": round(df["STOCHk_14_3_3"].iloc[-1], 2),
        "volume_ratio": round(df["Volume_Ratio"].iloc[-1], 2),
        "price_vs_ema50": "above" if current_price > df["EMA_50"].iloc[-1] else "below",
        "price_vs_ema200": "above" if current_price > df["EMA_200"].iloc[-1] else "below",
        "52w_high": round(df["High"].tail(252).max(), 2),
        "52w_low": round(df["Low"].tail(252).min(), 2),
        "pct_from_52w_high": round(
            (current_price - df["High"].tail(252).max()) / df["High"].tail(252).max() * 100, 2
        ),
    }

    backtest = run_all_bundles(symbol, days=90)
    backtest_summary = {
        name: {
            "win_rate": r.win_rate,
            "sharpe": r.sharpe_ratio,
            "avg_return": r.avg_return_pct,
            "signal": r.signal,
        }
        for name, r in backtest.items()
    }

    news = fetch_news(symbol, hours=48)
    news_classification = classify_news(symbol, news)
    reddit = get_reddit_sentiment(symbol, days=7)
    mf = get_mf_signal(symbol)
    fii = get_fii_dii_flow()

    return {
        "ohlcv_json": recent.to_json(),
        "indicators": indicators,
        "backtest_results": backtest_summary,
        "news_data": news,
        "news_classification": news_classification,
        "reddit_data": reddit,
        "mf_data": mf,
        "fii_data": fii,
        "current_price": current_price,
    }


def technical_node(state: AnalysisState) -> dict:
    output = run_technical_analysis(
        symbol=state["symbol"],
        indicators=state["indicators"],
        backtest_results=state["backtest_results"],
    )
    return {"technical_output": output}


def sentiment_node(state: AnalysisState) -> dict:
    output = run_sentiment_analysis(
        symbol=state["symbol"],
        news=state["news_data"],
        news_classification=state["news_classification"],
        reddit=state["reddit_data"],
    )
    return {"sentiment_output": output}


def smart_money_node(state: AnalysisState) -> dict:
    output = run_smart_money_analysis(
        symbol=state["symbol"],
        mf_data=state["mf_data"],
        fii_data=state["fii_data"],
    )
    return {"smart_money_output": output}


def risk_manager_node(state: AnalysisState) -> dict:
    tech = state["technical_output"]
    output = run_risk_management(
        symbol=state["symbol"],
        entry_price=state["current_price"],
        stop_loss=tech.get("stop_loss", state["current_price"] * 0.95),
        target=tech.get("target1", state["current_price"] * 1.10),
    )
    return {"risk_output": output}


def synthesizer_node(state: AnalysisState) -> dict:
    output = run_synthesis(
        symbol=state["symbol"],
        current_price=state["current_price"],
        technical=state["technical_output"],
        sentiment=state["sentiment_output"],
        smart_money=state["smart_money_output"],
        risk=state["risk_output"],
    )
    return {"recommendation": output}


def save_recommendation_node(state: AnalysisState) -> dict:
    """Persist the recommendation to PostgreSQL with new schema (entry_mid, hold_days_min/max)."""
    rec = state["recommendation"]
    entry_zone = rec.get("entry_zone", [None, None])
    entry_low, entry_high = entry_zone[0], entry_zone[1]
    entry_mid = rec.get("entry_mid")
    if entry_mid is None and entry_low is not None and entry_high is not None:
        entry_mid = round((float(entry_low) + float(entry_high)) / 2, 2)

    with SessionLocal() as db:
        row = Recommendation(
            symbol=state["symbol"],
            exchange=state.get("exchange", "NSE"),
            recommendation=rec.get("recommendation", "HOLD"),
            confidence=rec.get("confidence"),
            entry_low=entry_low,
            entry_high=entry_high,
            entry_mid=entry_mid,
            target1=rec.get("targets", [None, None])[0],
            target2=rec.get("targets", [None, None])[1],
            stop_loss=rec.get("stop_loss"),
            rr_ratio=rec.get("risk_reward"),
            hold_days_min=int(rec.get("hold_days_min", 5)),
            hold_days_max=int(rec.get("hold_days_max", 8)),
            strategy_used=rec.get("strategy"),
            technical_score=state["technical_output"].get("score"),
            sentiment_score=state["sentiment_output"].get("sentiment_score"),
            smart_money_score=state["smart_money_output"].get("confidence"),
            reasoning_text=rec.get("reasoning"),
            is_on_demand=True,
        )
        db.add(row)
        db.commit()
    return {}


# ── Graph construction ──────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("technical", technical_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("smart_money", smart_money_node)
    graph.add_node("risk_manager", risk_manager_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("save", save_recommendation_node)

    graph.set_entry_point("fetch_data")

    # fetch_data → parallel send to (technical, sentiment, smart_money)
    graph.add_edge("fetch_data", "technical")
    graph.add_edge("fetch_data", "sentiment")
    graph.add_edge("fetch_data", "smart_money")

    # Fan-in: risk_manager runs after all three parallel nodes complete.
    # LangGraph waits for all incoming edges before executing.
    graph.add_edge("technical", "risk_manager")
    graph.add_edge("sentiment", "risk_manager")
    graph.add_edge("smart_money", "risk_manager")

    graph.add_edge("risk_manager", "synthesizer")
    graph.add_edge("synthesizer", "save")
    graph.add_edge("save", END)

    return graph.compile()


_graph = build_graph()


# ── Top-level entry point ───────────────────────────────────────────────────

def run_analysis(symbol: str, exchange: str = "NSE") -> dict:
    """
    Run the full agent pipeline for a single symbol.

    Returns the synthesizer output dict, augmented with:
      - entry_mid: float = (entry_zone[0] + entry_zone[1]) / 2 (computed if missing)
      - analysis_time_sec: float = wall-clock time of the pipeline
      - current_price: float = price observed at fetch time
      - technical_output, sentiment_output, smart_money_output, risk_output: raw agent dicts
    """
    initial_state: AnalysisState = {
        "symbol": symbol.upper(),
        "exchange": exchange.upper(),
        "ohlcv_json": "",
        "indicators": {},
        "backtest_results": {},
        "news_data": [],
        "news_classification": {},
        "reddit_data": {},
        "mf_data": {},
        "fii_data": {},
        "current_price": 0.0,
        "technical_output": {},
        "sentiment_output": {},
        "smart_money_output": {},
        "risk_output": {},
        "recommendation": {},
        "error": None,
    }

    start = time.time()
    final_state = _graph.invoke(initial_state)
    elapsed = round(time.time() - start, 2)

    rec = dict(final_state.get("recommendation", {}))
    entry_zone = rec.get("entry_zone")
    if entry_zone and len(entry_zone) == 2 and rec.get("entry_mid") is None:
        rec["entry_mid"] = round((float(entry_zone[0]) + float(entry_zone[1])) / 2, 2)

    rec["analysis_time_sec"] = elapsed
    rec["current_price"] = final_state.get("current_price", 0.0)
    rec["technical_output"] = final_state.get("technical_output", {})
    rec["sentiment_output"] = final_state.get("sentiment_output", {})
    rec["smart_money_output"] = final_state.get("smart_money_output", {})
    rec["risk_output"] = final_state.get("risk_output", {})
    return rec
```

---

## Individual Agent Node Implementations

### `plutus/agents/technical.py`

```python
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
```

### `plutus/agents/sentiment.py`

```python
# plutus/agents/sentiment.py
from __future__ import annotations

import json

from plutus.agents.openrouter_client import call_llm
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
    return json.loads(response)
```

### `plutus/agents/smart_money.py`

```python
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
```

### `plutus/agents/risk_manager.py`

```python
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
```

### `plutus/agents/synthesizer.py`

```python
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
```

---

## Notes for Downstream Consumers

- **`run_analysis(symbol, exchange="NSE") -> dict`** is the only public entry point in this module.
- The returned dict always carries `entry_mid` and `analysis_time_sec`; callers should not recompute.
- The synthesizer schema split (`hold_days_min`, `hold_days_max`) is mandatory — the DB model and the outcome tracker both depend on it (see `04_database.md` and `_CHANGE_SPEC.md` §8).
- The 5-minute symbol cache lives one layer up in `plutus/api/cache.py` (see `09_api.md`); `run_analysis` itself is uncached.
