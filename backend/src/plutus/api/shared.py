from __future__ import annotations

import uuid
from datetime import date
from typing import Any, cast, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from plutus.api.auth import require_token
from plutus.api.deps import get_app_settings, get_db
from plutus.api.schemas.shared import (
    BacktestRequestIn,
    BacktestResultOut,
    BacktestTradeOut,
    BenchmarkResultOut,
    CalibrationRowOut,
    ChartBarOut,
    ChartDataOut,
    ChartSignalMarker,
    NotificationOut,
    PortfolioSnapshotOut,
    PositionSnapshotOut,
    RegimeSnapshotOut,
    RegimeVerdictOut,
    RunLogRowOut,
    RunOut,
)
from plutus.config.settings import Settings
from plutus.data.providers.angelone_provider import RateLimitSaturated, USER_RATE_LIMIT_TIMEOUT
from plutus.db.models import (
    AccumulationPosition,
    CalibrationRow,
    Fill,
    LatestPrice,
    Notification,
    RegimeSnapshot,
    RunLogRow,
    SwingSignal,
    SwingTrade,
    Tranche,
    Universe,
    WeeklyPostmortem,
)

router = APIRouter(prefix="/shared", tags=["shared"], dependencies=[Depends(require_token)])

# In-memory idempotency store: (key -> run_id). 24h TTL in spec; tests exercise the
# in-process dedup contract. A persistent store can replace this without API change.
_IDEMPOTENCY: dict[str, str] = {}


def _resolve_run(idempotency_key: str | None) -> str:
    if idempotency_key is not None and idempotency_key in _IDEMPOTENCY:
        return _IDEMPOTENCY[idempotency_key]
    run_id = str(uuid.uuid4())
    if idempotency_key is not None:
        _IDEMPOTENCY[idempotency_key] = run_id
    return run_id


@router.get("/regime", response_model=Optional[RegimeSnapshotOut])
def get_latest_regime(db: Session = Depends(get_db)) -> Optional[RegimeSnapshotOut]:
    row = db.execute(
        select(RegimeSnapshot).order_by(RegimeSnapshot.as_of_date.desc()).limit(1)
    ).scalars().first()
    if row is None:
        return None
    return RegimeSnapshotOut.model_validate(row, from_attributes=True)


@router.get("/regime/history", response_model=list[RegimeSnapshotOut])
def get_regime_history(
    days: int = Query(default=30, ge=1, le=3650),
    db: Session = Depends(get_db),
) -> list[RegimeSnapshotOut]:
    rows = db.execute(
        select(RegimeSnapshot).order_by(RegimeSnapshot.as_of_date.desc()).limit(days)
    ).scalars().all()
    return [RegimeSnapshotOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/universe", response_model=list[str])
def get_universe(
    as_of: date = Query(...),
    db: Session = Depends(get_db),
) -> list[str]:
    rows = db.execute(
        select(Universe.symbol)
        .where(Universe.as_of_date == as_of, Universe.in_universe.is_(True))
        .order_by(Universe.symbol)
    ).scalars().all()
    return list(rows)


@router.get("/calibration", response_model=list[CalibrationRowOut])
def list_calibration(
    db: Session = Depends(get_db),
) -> list[CalibrationRowOut]:
    """Return all calibration rows across all (bucket, regime) pairs.

    Used by the Calibration page to show pillar win-contribution charts
    and SPRT state for every active bundle.
    """
    rows = db.execute(
        select(CalibrationRow).order_by(
            CalibrationRow.bucket, CalibrationRow.regime
        )
    ).scalars().all()
    return [CalibrationRowOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/calibration/{bucket}/{regime}", response_model=CalibrationRowOut)
def get_calibration(
    bucket: str,
    regime: str,
    db: Session = Depends(get_db),
) -> CalibrationRowOut:
    row = db.execute(
        select(CalibrationRow).where(
            CalibrationRow.bucket == bucket, CalibrationRow.regime == regime
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="no calibration row")
    return CalibrationRowOut.model_validate(row, from_attributes=True)


@router.get("/run-log", response_model=list[RunLogRowOut])
def list_run_log(
    limit: int = Query(default=20, ge=1, le=100),
    job_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[RunLogRowOut]:
    """Return recent scheduler job run history.

    Used by the Dashboard to show last pipeline run status and timing.
    Ordered by most-recent first.
    """
    stmt = (
        select(RunLogRow)
        .order_by(RunLogRow.started_at.desc())
        .limit(limit)
    )
    if job_name is not None:
        stmt = stmt.where(RunLogRow.job_name == job_name)
    rows = db.execute(stmt).scalars().all()
    return [RunLogRowOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/benchmarks/latest", response_model=BenchmarkResultOut)
def get_latest_benchmarks(db: Session = Depends(get_db)) -> BenchmarkResultOut:
    row = db.execute(
        select(WeeklyPostmortem).order_by(WeeklyPostmortem.week_ending.desc()).limit(1)
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="no postmortem")
    # WeeklyPostmortem persists net-return columns only; profit factor and trade count
    # are computed by BenchmarkStrip at run time and not stored on this row. Report the
    # stored returns and the closed-trade count; profit factor surfaces via the live
    # backtest path, not this historical-snapshot endpoint.
    return BenchmarkResultOut(
        plutus_net_pct=row.swing_return_pct,
        nifty_net_pct=row.nifty_return_pct,
        regime_switched_net_pct=row.regime_switched_return_pct,
        random_liquid_net_pct=row.random_baseline_return_pct,
        plutus_profit_factor=0.0,
        plutus_n_trades=row.n_swing_trades_closed,
    )


def _add_indicators(df: "pd.DataFrame") -> "pd.DataFrame":
    """Compute all chart overlay indicators in-place and return df."""
    import numpy as np
    close = df["close"]
    df["dma20"] = close.rolling(20).mean()
    df["dma50"] = close.rolling(50).mean()
    df["dma200"] = close.rolling(200).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_mid"] = bb_mid
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["ema8"] = close.ewm(span=8, adjust=False).mean()
    df["ema13"] = close.ewm(span=13, adjust=False).mean()
    df["ema21"] = close.ewm(span=21, adjust=False).mean()
    df["ema34"] = close.ewm(span=34, adjust=False).mean()
    df["ema55"] = close.ewm(span=55, adjust=False).mean()
    dma20_prev = df["dma20"].shift(1)
    dma50_prev = df["dma50"].shift(1)
    df["golden_cross_20_50"] = (
        (df["dma20"] > df["dma50"]) & (dma20_prev <= dma50_prev)
    ).fillna(False)
    return df


def _df_to_bars(df: "pd.DataFrame", is_intraday: bool = False) -> "list[ChartBarOut]":
    import numpy as np
    import pandas as pd

    def _safe(v: object) -> float | None:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)

    bars = []
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["date"])
        date_str = ts.isoformat() if is_intraday else ts.date().isoformat()
        bars.append(ChartBarOut(
            date=date_str,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            dma20=_safe(row.get("dma20")),
            dma50=_safe(row.get("dma50")),
            dma200=_safe(row.get("dma200")),
            macd=_safe(row.get("macd")),
            macd_signal=_safe(row.get("macd_signal")),
            macd_hist=_safe(row.get("macd_hist")),
            bb_upper=_safe(row.get("bb_upper")),
            bb_lower=_safe(row.get("bb_lower")),
            bb_mid=_safe(row.get("bb_mid")),
            ema8=_safe(row.get("ema8")),
            ema13=_safe(row.get("ema13")),
            ema21=_safe(row.get("ema21")),
            ema34=_safe(row.get("ema34")),
            ema55=_safe(row.get("ema55")),
            golden_cross_20_50=bool(row.get("golden_cross_20_50", False)),
        ))
    return bars


@router.get("/chart/{symbol}", response_model=ChartDataOut)
def get_chart(
    symbol: str,
    signal_id: int | None = Query(default=None),
    days: int = Query(default=365, ge=3, le=365),
    db: Session = Depends(get_db),
) -> ChartDataOut:
    from datetime import timedelta

    import pandas as pd

    from plutus.config.settings import get_settings
    from plutus.data.providers.yfinance_provider import YFinanceProvider

    # --- Daily bars (Angel One preferred; yfinance fallback) ---
    end = date.today()
    fetch_days = max(days + 60, 300)
    start = end - timedelta(days=fetch_days)
    settings = get_settings()
    df = None
    if all([settings.angel_api_key, settings.angel_client_id,
            settings.angel_password, settings.angel_totp_secret]):
        try:
            from plutus.data.providers.angelone_provider import AngelOneProvider
            angel = AngelOneProvider(
                api_key=settings.angel_api_key,
                client_id=settings.angel_client_id,
                password=settings.angel_password,
                totp_secret=settings.angel_totp_secret,
                rate_limit_timeout=USER_RATE_LIMIT_TIMEOUT,
            )
            df = angel.fetch(symbol, start, end)
        except RateLimitSaturated:
            df = None  # fall through to yfinance — don't stall the browser
        except Exception:
            df = None
    if df is None or df.empty:
        try:
            df = YFinanceProvider().fetch(symbol, start, end)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"No chart data for {symbol}") from exc
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No chart data for {symbol}")
    df = _add_indicators(df)

    # latest price uses full history (not display slice) for accuracy
    close = df["close"]
    latest = close.iloc[-1]
    prev = close.iloc[-2] if len(close) > 1 else latest
    change_pct = ((latest - prev) / prev) * 100 if prev != 0 else 0.0

    display_df = df.iloc[-days:]
    bars = _df_to_bars(display_df, is_intraday=False)

    # --- Intraday bars (Angel One ONE_HOUR, 60 days) ---
    # Fetched once and cached on the client; duration switches are client-side slices.
    intraday_bars: list[ChartBarOut] = []
    if all([
        settings.angel_api_key,
        settings.angel_client_id,
        settings.angel_password,
        settings.angel_totp_secret,
    ]):
        try:
            from plutus.data.providers.angelone_provider import AngelOneProvider
            angel = AngelOneProvider(
                api_key=settings.angel_api_key,
                client_id=settings.angel_client_id,
                password=settings.angel_password,
                totp_secret=settings.angel_totp_secret,
                rate_limit_timeout=USER_RATE_LIMIT_TIMEOUT,
            )
            idf = angel.fetch_intraday(symbol, days=60, interval="ONE_HOUR")
            if not idf.empty:
                idf = _add_indicators(idf)
                intraday_bars = _df_to_bars(idf, is_intraday=True)
        except RateLimitSaturated:
            pass  # rate saturated — intraday_bars stays empty, daily bars still shown
        except Exception:
            pass  # graceful fallback: intraday_bars stays empty

    marker: ChartSignalMarker | None = None
    if signal_id is not None:
        sig = db.get(SwingSignal, signal_id)
        if sig is not None:
            marker = ChartSignalMarker(
                entry=float(sig.entry),
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                bundle=sig.bundle,
            )

    return ChartDataOut(
        symbol=symbol,
        latest_price=float(latest),
        latest_change_pct=round(change_pct, 2),
        bars=bars,
        intraday_bars=intraday_bars,
        signal_marker=marker,
    )


@router.get("/ltp/{symbol}")
def get_ltp(
    symbol: str,
    settings: Settings = Depends(get_app_settings),
    db: Session = Depends(get_db),
) -> dict:
    """Return latest traded price for a single symbol. Used by fill forms."""
    prices = _fetch_live_prices({symbol.upper()}, settings, db)
    price = prices.get(symbol.upper())
    if price is None:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    return {"symbol": symbol.upper(), "price": price}


@router.post("/runs/sunday", response_model=RunOut)
def run_sunday(idempotency_key: str | None = Header(default=None)) -> RunOut:
    import logging
    import threading

    from plutus.pipeline.sunday import run_sunday_pipeline

    _log = logging.getLogger(__name__)
    run_id = _resolve_run(idempotency_key)

    def _run() -> None:
        try:
            result = run_sunday_pipeline()
            if result.errors:
                _log.error("sunday_pipeline errors: %s", result.errors)
            else:
                _log.info("sunday_pipeline done: %d signals written", result.signals_written)
        except Exception:
            _log.exception("sunday_pipeline crashed")

    threading.Thread(target=_run, daemon=True).start()
    return RunOut(run_id=run_id)


@router.post("/runs/monday-revalidation", response_model=RunOut)
def run_monday_revalidation(
    idempotency_key: str | None = Header(default=None),
) -> RunOut:
    return RunOut(run_id=_resolve_run(idempotency_key))


@router.post("/runs/midweek-mini", response_model=RunOut)
def run_midweek_mini(
    idempotency_key: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> RunOut:
    if not settings.midweek_mini_screen_enabled:
        raise HTTPException(status_code=409, detail="midweek mini-screen disabled")
    return RunOut(run_id=_resolve_run(idempotency_key))


@router.post("/backtest", response_model=BacktestResultOut)
def run_backtest(payload: BacktestRequestIn) -> BacktestResultOut:
    """Run a single-symbol backtest using the Strategy Lab service.

    Walks `lookback_days` of OHLCV (yfinance) through the chosen bundle and
    returns aggregate stats + per-trade rows. Synchronous; typical runs are
    under ~10s. PEAD/SMC are gated by spec C2/C3 and rejected here.
    """
    from plutus.dashboard.backtest_service import (
        BUNDLE_FACTORIES,
        run_single_symbol_backtest,
    )

    bundle = payload.bundle.strip().lower()
    symbol = payload.symbol.strip().upper()
    if bundle not in BUNDLE_FACTORIES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Bundle '{bundle}' not supported in the lab "
                f"(allowed: {sorted(BUNDLE_FACTORIES)}; pead/smc gated by C2/C3)"
            ),
        )
    if payload.lookback_days < 30 or payload.lookback_days > 1825:
        raise HTTPException(status_code=400, detail="lookback_days must be 30..1825")

    try:
        summary = run_single_symbol_backtest(
            bundle_name=bundle,
            symbol=symbol,
            lookback_days=payload.lookback_days,
            use_cost_model=payload.use_cost_model,
            use_fill_policy=payload.use_fill_policy,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    trades_out: list[BacktestTradeOut] = []
    if not summary.trades_df.empty:
        for row in summary.trades_df.to_dict(orient="records"):
            trades_out.append(
                BacktestTradeOut(
                    entry_date=str(row["entry_date"]),
                    exit_date=str(row["exit_date"]),
                    hold_days=int(row["hold_days"]),
                    realized_R=float(row["realized_R"]),
                )
            )

    return BacktestResultOut(
        bundle=summary.bundle,
        symbol=summary.symbol,
        start=summary.start,
        end=summary.end,
        n_trades=summary.n_trades,
        win_rate=summary.win_rate,
        expectancy_R=summary.expectancy_R,
        sum_R=summary.sum_R,
        avg_hold_days=summary.avg_hold_days,
        fills_before_signal=summary.fills_before_signal,
        cost_model_on=summary.cost_model_on,
        fill_policy_on=summary.fill_policy_on,
        trades=trades_out,
    )


def _fetch_live_prices(
    symbols: set[str],
    settings: Settings,
    db: Session,
) -> dict[str, float]:
    """Fetch LTP via Angel One → yfinance → cached LatestPrice table (stale fallback)."""
    import logging
    from datetime import datetime, timedelta
    from decimal import Decimal as D

    logger = logging.getLogger(__name__)
    prices: dict[str, float] = {}
    source = "angelone"

    if settings.angel_api_key and settings.angel_client_id:
        try:
            from plutus.data.providers.angelone_provider import AngelOneProvider

            provider = AngelOneProvider(
                api_key=settings.angel_api_key,
                client_id=settings.angel_client_id,
                password=settings.angel_password,
                totp_secret=settings.angel_totp_secret,
                rate_limit_timeout=USER_RATE_LIMIT_TIMEOUT,
            )
            prices = provider.fetch_ltp_batch(list(symbols))
        except RateLimitSaturated:
            logger.warning("angel_one_batch_rate_saturated — falling back to yfinance")
        except Exception:
            logger.warning("angel_one_batch_failed, falling back to yfinance", exc_info=True)

    missing = symbols - prices.keys()
    if missing:
        source = "yfinance" if not prices else source
        from plutus.data.providers.yfinance_provider import YFinanceProvider

        yf_provider = YFinanceProvider()
        today = date.today()
        start = today - timedelta(days=5)
        for sym in missing:
            try:
                df = yf_provider.fetch(sym, start, today)
                if not df.empty:
                    prices[sym] = float(df["close"].iloc[-1])
            except Exception:
                logger.warning("yfinance_fallback_failed: %s", sym)

    # Last resort: read stale cached prices from the LatestPrice table so that
    # the portfolio snapshot is never silently empty when live sources are down.
    still_missing = symbols - prices.keys()
    if still_missing:
        cached_rows = db.execute(
            select(LatestPrice).where(LatestPrice.symbol.in_(still_missing))
        ).scalars().all()
        for row in cached_rows:
            prices[row.symbol] = float(row.price)
            logger.info("using_cached_price: %s = %.2f (from %s)", row.symbol, float(row.price), row.fetched_at)

    now = datetime.utcnow()
    for sym, price in prices.items():
        # Only write back to cache if the price came from a live source
        if sym not in still_missing:
            row = db.execute(
                select(LatestPrice).where(LatestPrice.symbol == sym)
            ).scalars().first()
            if row:
                row.price = D(str(round(price, 2)))
                row.source = source
                row.fetched_at = now
            else:
                db.add(LatestPrice(
                    symbol=sym,
                    price=D(str(round(price, 2))),
                    source=source,
                    fetched_at=now,
                ))
    db.flush()
    return prices


@router.get("/portfolio-snapshot", response_model=PortfolioSnapshotOut)
def get_portfolio_snapshot(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> PortfolioSnapshotOut:
    from datetime import datetime

    positions: list[PositionSnapshotOut] = []
    total_invested = 0.0
    total_current = 0.0

    open_trades = db.execute(
        select(SwingTrade).where(SwingTrade.state.in_(["OPEN", "T1_HIT"]))
    ).scalars().all()

    symbols_needed = {t.symbol for t in open_trades}
    accum_positions = db.execute(
        select(AccumulationPosition).where(
            AccumulationPosition.state.in_(["BUILDING", "FULL"])
        )
    ).scalars().all()
    symbols_needed.update(p.symbol for p in accum_positions)

    prices = _fetch_live_prices(symbols_needed, settings, db)

    for trade in open_trades:
        signal = db.get(SwingSignal, trade.signal_id)
        price = prices.get(trade.symbol)
        if price is None or signal is None:
            continue
        entry_fills = db.execute(
            select(Fill).where(
                Fill.trade_id == trade.id,
                Fill.side == "BUY",
            )
        ).scalars().all()
        if not entry_fills:
            avg_cost = float(signal.entry)
        else:
            total_cost = sum(float(f.price) * f.qty for f in entry_fills)
            total_qty = sum(f.qty for f in entry_fills)
            avg_cost = total_cost / total_qty if total_qty else float(signal.entry)
        invested = avg_cost * trade.qty
        current = price * trade.qty
        total_invested += invested
        total_current += current
        sl = float(signal.stop_loss)
        sl_dist = ((price - sl) / price) * 100 if price > 0 else None
        positions.append(PositionSnapshotOut(
            symbol=trade.symbol,
            mode="swing",
            qty=trade.qty,
            avg_cost=round(avg_cost, 2),
            current_price=round(price, 2),
            pnl=round(current - invested, 2),
            pnl_pct=round(((current - invested) / invested) * 100, 2) if invested else 0.0,
            stop_loss=sl,
            sl_distance_pct=round(sl_dist, 2) if sl_dist is not None else None,
        ))

    for pos in accum_positions:
        price = prices.get(pos.symbol)
        if price is None or pos.qty_total <= 0:
            continue
        avg_cost = float(pos.avg_cost)
        invested = avg_cost * pos.qty_total
        current = price * pos.qty_total
        total_invested += invested
        total_current += current
        positions.append(PositionSnapshotOut(
            symbol=pos.symbol,
            mode="accumulation",
            qty=pos.qty_total,
            avg_cost=round(avg_cost, 2),
            current_price=round(price, 2),
            pnl=round(current - invested, 2),
            pnl_pct=round(((current - invested) / invested) * 100, 2) if invested else 0.0,
        ))

    pnl = total_current - total_invested
    return PortfolioSnapshotOut(
        positions=positions,
        total_invested=round(total_invested, 2),
        total_current=round(total_current, 2),
        total_pnl=round(pnl, 2),
        total_pnl_pct=round((pnl / total_invested) * 100, 2) if total_invested else 0.0,
        checked_at=datetime.utcnow(),
    )


@router.post("/portfolio-snapshot/check")
def run_hourly_price_check(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, object]:
    """Triggered by scheduler or manually. Fetches prices via Angel One, creates SL/T1 notifications."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    created_count = 0

    open_trades = db.execute(
        select(SwingTrade).where(SwingTrade.state.in_(["OPEN", "T1_HIT"]))
    ).scalars().all()
    symbols_needed = {t.symbol for t in open_trades}

    accum_positions = db.execute(
        select(AccumulationPosition).where(
            AccumulationPosition.state.in_(["BUILDING", "FULL"])
        )
    ).scalars().all()
    symbols_needed.update(p.symbol for p in accum_positions)

    prices = _fetch_live_prices(symbols_needed, settings, db)

    for trade in open_trades:
        signal = db.get(SwingSignal, trade.signal_id)
        if signal is None:
            continue
        price = prices.get(trade.symbol)
        if price is None:
            continue

        sl = float(signal.stop_loss)
        entry = float(signal.entry)
        risk = entry - sl
        if risk <= 0:
            continue
        sl_distance_pct = ((price - sl) / price) * 100 if price > 0 else 100

        if sl_distance_pct <= 3.0:
            recent = db.execute(
                select(Notification).where(
                    Notification.symbol == trade.symbol,
                    Notification.kind == "SL_PROXIMITY",
                    Notification.dismissed.is_(False),
                    Notification.created_at >= now - timedelta(hours=2),
                )
            ).scalars().first()
            if recent is None:
                db.add(Notification(
                    kind="SL_PROXIMITY",
                    severity="URGENT" if sl_distance_pct <= 1.0 else "WARNING",
                    title=f"{trade.symbol} near stop loss",
                    body=f"Price ₹{price:,.2f} is {sl_distance_pct:.1f}% from SL ₹{sl:,.2f}",
                    symbol=trade.symbol,
                    created_at=now,
                ))
                created_count += 1

        t1 = float(signal.target_1)
        t1_distance_pct = ((t1 - price) / price) * 100 if price > 0 else 100
        if t1_distance_pct <= 2.0 and trade.state == "OPEN":
            recent = db.execute(
                select(Notification).where(
                    Notification.symbol == trade.symbol,
                    Notification.kind == "T1_PROXIMITY",
                    Notification.dismissed.is_(False),
                    Notification.created_at >= now - timedelta(hours=2),
                )
            ).scalars().first()
            if recent is None:
                db.add(Notification(
                    kind="T1_PROXIMITY",
                    severity="INFO",
                    title=f"{trade.symbol} approaching T1",
                    body=f"Price ₹{price:,.2f} is {t1_distance_pct:.1f}% from T1 ₹{t1:,.2f}",
                    symbol=trade.symbol,
                    created_at=now,
                ))
                created_count += 1

    db.flush()
    return {"notifications_created": created_count, "checked_at": now.isoformat()}


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    include_dismissed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    q = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if not include_dismissed:
        q = q.where(Notification.dismissed.is_(False))
    rows = db.execute(q).scalars().all()
    return [NotificationOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/notifications/{notification_id}/dismiss")
def dismiss_notification(
    notification_id: int,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(status_code=404, detail="notification not found")
    n.dismissed = True
    db.flush()
    return {"status": "dismissed"}


@router.post("/test-telegram")
def test_telegram(
    settings: Settings = Depends(get_app_settings),
    session: object = Depends(get_db),
) -> dict[str, object]:
    if settings.telegram_bot_token is None:
        return {"sent": False, "reason": "no telegram token configured"}
    from datetime import datetime

    from plutus.alerts.channels import AlertMessage
    from plutus.alerts.factory import build_alert_monitor
    monitor = build_alert_monitor(settings)
    monitor.emit(
        AlertMessage(
            kind="ENTRY",
            symbol=None,
            title="Plutus test",
            body_md="Test from dashboard",
            severity="INFO",
            deduplication_key="test",
        ),
        now=datetime.utcnow(),
        session=session,
    )
    return {"sent": True}
