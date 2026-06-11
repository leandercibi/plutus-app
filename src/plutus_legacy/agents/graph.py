# plutus/agents/graph.py
from __future__ import annotations

import time
from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from plutus.agents.risk_manager import run_risk_management
from plutus.agents.scoring import compute_score
from plutus.agents.sentiment import run_sentiment_analysis
from plutus.agents.smart_money import run_smart_money_analysis
from plutus.agents.synthesizer import run_synthesis
from plutus.agents.technical import run_technical_analysis
from plutus.backtesting.runner import run_all_bundles
from plutus.data.news import classify_news, fetch_news
from plutus.data.ohlcv import add_indicators, fetch_ohlcv
from plutus.data.reddit import get_reddit_sentiment
from plutus.data.regime import get_nifty_regime, get_sector_strength
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
    regime_data: dict  # {trend, slope, distance_from_ema50_pct, sector_rs}
    best_bundle_sharpe: float
    _indicator_df: (
        object  # indicator DataFrame; produced by fetch_data, consumed by scoring
    )
    # Agent outputs
    technical_output: dict
    sentiment_output: dict
    smart_money_output: dict
    risk_output: dict
    # Scoring (deterministic)
    score_breakdown: Optional[object]  # ScoreBreakdown instance
    classification: Optional[str]  # Classification.value
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

    def _last(col: str, decimals: int = 2) -> float:
        """Safely get last value of a column; returns None if column absent."""
        if col not in df.columns:
            return None
        v = df[col].iloc[-1]
        import math

        return (
            round(float(v), decimals) if v is not None and not math.isnan(v) else None
        )

    indicators = {
        "current_price": round(current_price, 2),
        "ema9": _last("EMA_9"),
        "ema21": _last("EMA_21"),
        "ema50": _last("EMA_50"),
        "ema200": _last("EMA_200"),
        "rsi": _last("RSI_14"),
        "macd": _last("MACD_12_26_9", 4),
        "macd_signal": _last("MACDs_12_26_9", 4),
        "macd_hist": _last("MACDh_12_26_9", 4),
        "bb_lower": _last("BBL_20_2.0"),
        "bb_mid": _last("BBM_20_2.0"),
        "bb_upper": _last("BBU_20_2.0"),
        "atr": _last("ATRr_14"),
        "adx": _last("ADX_14"),
        "stoch_k": _last("STOCHk_14_3_3"),
        "volume_ratio": _last("Volume_Ratio"),
        "price_vs_ema50": (
            (
                "above"
                if _last("EMA_50") and current_price > _last("EMA_50")
                else "below"
            )
            if "EMA_50" in df.columns
            else None
        ),
        "price_vs_ema200": (
            (
                "above"
                if _last("EMA_200") and current_price > _last("EMA_200")
                else "below"
            )
            if "EMA_200" in df.columns
            else None
        ),
        "52w_high": round(df["High"].tail(252).max(), 2),
        "52w_low": round(df["Low"].tail(252).min(), 2),
        "pct_from_52w_high": round(
            (current_price - df["High"].tail(252).max())
            / df["High"].tail(252).max()
            * 100,
            2,
        ),
    }

    backtest = run_all_bundles(symbol, days=90)
    best_sharpe = max(
        (r.sharpe_ratio for r in backtest.values() if r.total_trades > 0),
        default=0.0,
    )
    backtest_summary = {
        name: {
            "win_rate": r.win_rate,
            "sharpe": r.sharpe_ratio,
            "avg_return": r.avg_return_pct,
            "total_trades": r.total_trades,
        }
        for name, r in backtest.items()
    }

    news = fetch_news(symbol, hours=48)
    news_classification = classify_news(symbol, news)
    reddit = get_reddit_sentiment(symbol, days=7)
    mf = get_mf_signal(symbol)
    fii = get_fii_dii_flow()

    try:
        regime = get_nifty_regime()
        sector_rs = get_sector_strength()
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("regime fetch failed: %s", e)
        regime = {"trend": "UNKNOWN", "slope": 0.0, "distance_from_ema50_pct": 0.0}
        sector_rs = {}

    regime_data = {**regime, "sector_rs": sector_rs}

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
        "regime_data": regime_data,
        "best_bundle_sharpe": best_sharpe,
        "_indicator_df": df,  # indicator DataFrame; consumed by scoring_node
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
    tech = state.get("technical_output") or {}
    price = state.get("current_price") or 0.0
    output = run_risk_management(
        symbol=state["symbol"],
        entry_price=price,
        stop_loss=tech.get("stop_loss", price * 0.95),
        target=tech.get("target1", price * 1.10),
    )
    return {"risk_output": output or {}}


def scoring_node(state: AnalysisState) -> dict:
    """Deterministic scoring — no LLM. Returns ScoreBreakdown + Classification."""
    tech_out = state.get("technical_output", {})
    risk_out = state.get("risk_output", {})
    sent_out = state.get("sentiment_output", {})
    sm_out = state.get("smart_money_output", {})
    regime = state.get("regime_data", {})

    indicator_df = state.get("_indicator_df")

    # Build news dict for sentiment_pillar from the sentiment agent's output
    news_for_pillar = {
        "sentiment_score": sent_out.get("sentiment_score", 0),
        "sentiment_label": sent_out.get("sentiment_label", "neutral"),
        "is_material_event": sent_out.get("is_material_event", False),
        "material_event_type": sent_out.get("material_event_type"),
    }

    fii_for_pillar = {"fii_signal": sm_out.get("fii_signal", "unknown")}
    dii_for_pillar = {"dii_signal": sm_out.get("dii_signal", "unknown")}
    mf_for_pillar = {
        "verdict": sm_out.get("verdict", "UNKNOWN"),
        "mf_count_accumulating": sm_out.get("mf_count_accumulating", 0),
        "mf_count_reducing": sm_out.get("mf_count_reducing", 0),
    }

    levels = {
        "entry": tech_out.get("entry_zone", [state.get("current_price", 0)] * 2)[0],
        "stop": tech_out.get("stop_loss", state.get("current_price", 0) * 0.95),
        "t1": tech_out.get("target1", state.get("current_price", 0) * 1.10),
        "t2": tech_out.get("target2", state.get("current_price", 0) * 1.15),
    }

    sector = regime.get("sector")  # may be None; regime_pillar handles it
    sector_rs = regime.get("sector_rs", {})
    nifty_regime = {k: v for k, v in regime.items() if k != "sector_rs"}

    position_size = float(risk_out.get("shares", 1) or 1)

    breakdown, cls = compute_score(
        symbol=state["symbol"],
        indicator_df=indicator_df,
        levels=levels,
        news=news_for_pillar,
        fii=fii_for_pillar,
        dii=dii_for_pillar,
        mf=mf_for_pillar,
        nifty_regime=nifty_regime,
        sector=sector,
        sector_rs=sector_rs,
        best_bundle_sharpe=state.get("best_bundle_sharpe", 0.0),
        position_size=position_size,
    )

    return {
        "score_breakdown": breakdown,
        "classification": cls.value,
    }


def narrative_node(state: AnalysisState) -> dict:
    """LLM writes the thesis narrative; recommendation comes from scoring_node."""
    from plutus.agents.scoring import Classification, ScoreBreakdown

    breakdown: ScoreBreakdown = state["score_breakdown"]
    cls = Classification(state["classification"])

    narrative_payload = run_synthesis(
        symbol=state["symbol"],
        breakdown=breakdown,
        classification=cls,
        current_price=state.get("current_price", 0.0),
        technical_output=state.get("technical_output"),
        sentiment_output=state.get("sentiment_output"),
        smart_money_output=state.get("smart_money_output"),
        risk_output=state.get("risk_output"),
    )

    tech_out = state.get("technical_output") or {}
    risk_out = state.get("risk_output") or {}
    entry_zone = tech_out.get("entry_zone", [state.get("current_price", 0)] * 2)
    entry_low, entry_high = entry_zone[0], (
        entry_zone[1] if len(entry_zone) > 1 else entry_zone[0]
    )
    entry_mid = round((float(entry_low) + float(entry_high)) / 2, 2)

    # Build a human-readable strategy string from backtest results (top 2 by Sharpe)
    backtest = state.get("backtest_results") or {}
    top_bundles = sorted(
        [
            (k, v["sharpe"])
            for k, v in backtest.items()
            if isinstance(v, dict) and v.get("total_trades", 0) > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )[:2]
    strategy_str = (
        " + ".join(k.replace("bundle_", "").title() for k, _ in top_bundles)
        if top_bundles
        else "N/A"
    )

    recommendation = {
        "recommendation": cls.value,
        "confidence": breakdown.composite,  # composite score on 0-100 scale
        "composite_score": breakdown.composite,
        "sub_scores": {
            "technical": breakdown.technical,
            "smart_money": breakdown.smart_money,
            "sentiment": breakdown.sentiment,
            "regime": breakdown.regime,
            "rr": breakdown.rr,
        },
        "entry_zone": entry_zone,
        "entry_mid": entry_mid,
        "targets": [tech_out.get("target1"), tech_out.get("target2")],
        "stop_loss": tech_out.get("stop_loss"),
        "risk_reward": tech_out.get("rr_ratio"),
        "position": {
            "shares": risk_out.get("shares", 0),
            "capital": risk_out.get("capital_used", 0),
            "pct_of_portfolio": risk_out.get("pct_of_capital", 0),
            "max_loss_inr": risk_out.get("max_loss_inr", 0),
        },
        "hold_days_min": 5,
        "hold_days_max": 8,
        "hold_days": f"{5}-{8}",
        "strategy": strategy_str,
        "risk_flags": narrative_payload.get("top_3_risk_flags", []),
        "reasoning": narrative_payload.get("narrative", ""),
    }

    return {"recommendation": recommendation}


def save_recommendation_node(state: AnalysisState) -> dict:
    """Persist the recommendation with all sub-scores from scoring.py."""
    rec = state["recommendation"]
    entry_zone = rec.get("entry_zone") or [None, None]
    entry_low = entry_zone[0] if len(entry_zone) > 0 else None
    entry_high = entry_zone[1] if len(entry_zone) > 1 else None
    entry_mid = rec.get("entry_mid")
    if entry_mid is None and entry_low is not None and entry_high is not None:
        entry_mid = round((float(entry_low) + float(entry_high)) / 2, 2)

    sub = rec.get("sub_scores", {})
    targets = rec.get("targets") or [None, None]

    with SessionLocal() as db:
        row = Recommendation(
            symbol=state["symbol"],
            exchange=state.get("exchange", "NSE"),
            recommendation=rec.get("recommendation", "HOLD"),
            confidence=rec.get("composite_score"),
            entry_low=entry_low,
            entry_high=entry_high,
            entry_mid=entry_mid,
            target1=targets[0] if targets else None,
            target2=targets[1] if len(targets) > 1 else None,
            stop_loss=rec.get("stop_loss"),
            rr_ratio=rec.get("risk_reward"),
            hold_days_min=int(rec.get("hold_days_min", 5)),
            hold_days_max=int(rec.get("hold_days_max", 8)),
            strategy_used=str(rec.get("strategy", ""))[:200],
            technical_score=sub.get("technical"),
            sentiment_score=sub.get("sentiment"),
            smart_money_score=sub.get("smart_money"),
            regime_score=sub.get("regime"),
            rr_score=sub.get("rr"),
            reasoning_text=rec.get("reasoning"),
            is_on_demand=True,
        )
        db.add(row)
        db.commit()
    return {"symbol": state["symbol"]}


# ── Graph construction ──────────────────────────────────────────────────────


def build_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("technical", technical_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("smart_money", smart_money_node)
    graph.add_node("risk_manager", risk_manager_node)
    graph.add_node("scoring", scoring_node)
    graph.add_node("narrative", narrative_node)
    graph.add_node("save", save_recommendation_node)

    graph.set_entry_point("fetch_data")

    # fetch_data → parallel send to (technical, sentiment, smart_money)
    graph.add_edge("fetch_data", "technical")
    graph.add_edge("fetch_data", "sentiment")
    graph.add_edge("fetch_data", "smart_money")

    # Fan-in: risk_manager runs after all three parallel nodes complete.
    graph.add_edge("technical", "risk_manager")
    graph.add_edge("sentiment", "risk_manager")
    graph.add_edge("smart_money", "risk_manager")

    # Deterministic scoring → narrative (LLM) → save
    graph.add_edge("risk_manager", "scoring")
    graph.add_edge("scoring", "narrative")
    graph.add_edge("narrative", "save")
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
        "regime_data": {},
        "best_bundle_sharpe": 0.0,
        "_indicator_df": None,
        "technical_output": {},
        "sentiment_output": {},
        "smart_money_output": {},
        "risk_output": {},
        "score_breakdown": None,
        "classification": None,
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
