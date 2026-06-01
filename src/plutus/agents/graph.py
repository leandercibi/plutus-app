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
