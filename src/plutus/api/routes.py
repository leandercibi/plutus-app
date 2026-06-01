# api/routes.py
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, List
from plutus.config import settings
from plutus.agents.graph import run_analysis
from plutus.db.session import SessionLocal
from plutus.db.models import Recommendation, WeeklyRun
import time

router = APIRouter()


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ── Request / Response Models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="NSE stock symbol e.g. RELIANCE, INFY, TATAMOTORS")
    exchange: str = Field("NSE", description="NSE or BSE")


class PositionModel(BaseModel):
    shares: int
    capital: float
    pct_of_portfolio: float
    max_loss_inr: float


class SignalsModel(BaseModel):
    technical: dict
    sentiment: dict
    smart_money: dict


class AnalyzeResponse(BaseModel):
    symbol: str
    exchange: str
    current_price: float
    recommendation: str          # BUY | SELL | HOLD | WATCH | AVOID
    confidence: float            # 0–10
    entry_zone: List[float]      # [low, high]
    targets: List[float]         # [target1, target2]
    stop_loss: float
    risk_reward: float
    position: PositionModel
    hold_days: str               # e.g. "5-8"
    strategy: str
    signals: SignalsModel
    risk_flags: List[str]
    reasoning: str
    analysis_time_sec: float


class WeeklyRecommendation(BaseModel):
    symbol: str
    recommendation: str
    confidence: float
    entry_zone: List[Optional[float]]
    targets: List[Optional[float]]
    stop_loss: Optional[float]
    reasoning: str


class WeeklyResponse(BaseModel):
    run_date: str
    market_regime: str
    strategy_selected: str
    buy_signals: List[WeeklyRecommendation]
    watch_signals: List[WeeklyRecommendation]
    total_screened: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_stock(
    request: AnalyzeRequest,
    _: str = Depends(verify_api_key),
):
    """
    Run full agent pipeline for a single stock.
    Used by Hermes agent as an AI tool.
    Takes ~15-25 seconds to complete.
    """
    symbol = request.symbol.upper().strip()
    exchange = request.exchange.upper()

    start_time = time.time()
    try:
        result = run_analysis(symbol, exchange)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Analysis failed: {str(e)}")

    elapsed = round(time.time() - start_time, 1)

    return AnalyzeResponse(
        symbol=symbol,
        exchange=exchange,
        current_price=result.get("current_price", 0),
        recommendation=result.get("recommendation", "HOLD"),
        confidence=result.get("confidence", 0),
        entry_zone=result.get("entry_zone", [0, 0]),
        targets=result.get("targets", [0, 0]),
        stop_loss=result.get("stop_loss", 0),
        risk_reward=result.get("risk_reward", 0),
        position=PositionModel(**result.get("position", {"shares": 0, "capital": 0, "pct_of_portfolio": 0, "max_loss_inr": 0})),
        hold_days=result.get("hold_days", "N/A"),
        strategy=result.get("strategy", ""),
        signals=SignalsModel(
            technical=result.get("technical_output", {}),
            sentiment=result.get("sentiment_output", {}),
            smart_money=result.get("smart_money_output", {}),
        ),
        risk_flags=result.get("risk_flags", []),
        reasoning=result.get("reasoning", ""),
        analysis_time_sec=elapsed,
    )


@router.get("/weekly", response_model=WeeklyResponse)
async def get_weekly_recommendations(
    _: str = Depends(verify_api_key),
):
    """
    Returns the latest weekly recommendation set.
    Does NOT trigger a new analysis — returns stored results.
    """
    with SessionLocal() as db:
        latest_run = db.query(WeeklyRun)\
            .order_by(WeeklyRun.run_date.desc()).first()

        if not latest_run:
            raise HTTPException(status_code=404, detail="No weekly run found yet")

        recs = db.query(Recommendation)\
            .filter(Recommendation.weekly_run_id == latest_run.id)\
            .order_by(Recommendation.confidence.desc()).all()

        buy_signals = [
            WeeklyRecommendation(
                symbol=r.symbol,
                recommendation=r.recommendation.value,
                confidence=r.confidence or 0,
                entry_zone=[r.entry_low, r.entry_high],
                targets=[r.target1, r.target2],
                stop_loss=r.stop_loss,
                reasoning=r.reasoning_text or "",
            )
            for r in recs if r.recommendation.value == "BUY"
        ]

        watch_signals = [
            WeeklyRecommendation(
                symbol=r.symbol,
                recommendation=r.recommendation.value,
                confidence=r.confidence or 0,
                entry_zone=[r.entry_low, r.entry_high],
                targets=[r.target1, r.target2],
                stop_loss=r.stop_loss,
                reasoning=r.reasoning_text or "",
            )
            for r in recs if r.recommendation.value == "WATCH"
        ]

        return WeeklyResponse(
            run_date=str(latest_run.run_date),
            market_regime=latest_run.market_regime or "UNKNOWN",
            strategy_selected=latest_run.strategy_selected or "",
            buy_signals=buy_signals,
            watch_signals=watch_signals,
            total_screened=latest_run.stocks_screened or 0,
        )


@router.get("/health")
async def health_check():
    """Liveness check. No auth required."""
    from datetime import datetime
    return {
        "status": "ok",
        "service": "Plutus Trading Engine",
        "timestamp": datetime.utcnow().isoformat(),
    }
