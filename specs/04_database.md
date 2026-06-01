# 04 — Database Schema & Models

This document is the single source of truth for the Plutus PostgreSQL schema. Every table is shown twice: once as raw SQL (`CREATE TABLE ...`) and once as a SQLAlchemy ORM class. The two **must stay in sync**. If you change one, change the other in the same edit.

Module path convention: all imports use the top-level `plutus` package, e.g. `from plutus.db.session import Base`.

---

## PostgreSQL Setup (run once)

```sql
CREATE USER plutus WITH PASSWORD 'plutus';
CREATE DATABASE plutus_db OWNER plutus;
GRANT ALL PRIVILEGES ON DATABASE plutus_db TO plutus;
```

---

## Enum Types

Postgres-side enum types (created automatically by SQLAlchemy when `native_enum=True`, shown here for documentation parity):

```sql
CREATE TYPE recommendation_verdict AS ENUM ('BUY', 'SELL', 'HOLD', 'WATCH', 'AVOID');
CREATE TYPE trade_direction       AS ENUM ('LONG', 'SHORT');
CREATE TYPE trade_status          AS ENUM ('OPEN', 'CLOSED');
CREATE TYPE trade_exit_reason     AS ENUM ('TARGET1', 'TARGET2', 'STOP', 'MANUAL', 'SIGNAL', 'EXPIRED');
CREATE TYPE outcome_verdict       AS ENUM ('HIT_T1', 'HIT_T2', 'STOPPED', 'EXPIRED', 'PENDING');
```

Python-side enums (lives at the top of `src/plutus/db/models.py`):

```python
import enum


class RecommendationVerdict(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WATCH = "WATCH"
    AVOID = "AVOID"


class TradeDirection(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TradeExitReason(str, enum.Enum):
    TARGET1 = "TARGET1"
    TARGET2 = "TARGET2"
    STOP = "STOP"
    MANUAL = "MANUAL"
    SIGNAL = "SIGNAL"
    EXPIRED = "EXPIRED"


class OutcomeVerdict(str, enum.Enum):
    HIT_T1 = "HIT_T1"
    HIT_T2 = "HIT_T2"
    STOPPED = "STOPPED"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"
```

The shared `models.py` preamble (imports + enums above) is assumed at the top of every ORM block below; only the per-table model body is repeated for each section.

```python
# src/plutus/db/models.py — preamble
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, Boolean, DateTime,
    Text, ForeignKey, Enum as SAEnum, Date, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from plutus.db.session import Base
# ... enum classes from above ...
```

---

## Table: `weekly_runs`

One row per Sunday research run.

```sql
CREATE TABLE weekly_runs (
    id                   SERIAL PRIMARY KEY,
    run_date             DATE NOT NULL UNIQUE,             -- Sunday date
    market_regime        VARCHAR(50),                      -- 'BULLISH' | 'BEARISH' | 'SIDEWAYS'
    nifty_trend          VARCHAR(50),                      -- 'ABOVE_EMA50' | 'BELOW_EMA50'
    strategy_selected    VARCHAR(200),                     -- JSON string of bundle names + weights
    stocks_screened      INTEGER,
    stocks_analysed      INTEGER,
    total_buy_signals    INTEGER DEFAULT 0,
    total_watch_signals  INTEGER DEFAULT 0,
    report_md_path       VARCHAR(500),
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

```python
class WeeklyRun(Base):
    __tablename__ = "weekly_runs"

    id = Column(Integer, primary_key=True)
    run_date = Column(Date, nullable=False, unique=True)        # Sunday date
    market_regime = Column(String(50))                          # 'BULLISH' / 'BEARISH' / 'SIDEWAYS'
    nifty_trend = Column(String(50))                            # 'ABOVE_EMA50' / 'BELOW_EMA50'
    strategy_selected = Column(String(200))                     # JSON string of bundle names + weights
    stocks_screened = Column(Integer)
    stocks_analysed = Column(Integer)
    total_buy_signals = Column(Integer, default=0)
    total_watch_signals = Column(Integer, default=0)
    report_md_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

    recommendations = relationship("Recommendation", back_populates="weekly_run")
```

---

## Table: `recommendations`

One row per stock per run (and per `/analyze` ad-hoc call). Includes outcome-tracking columns and the Monday revalidation columns.

`entry_mid` is the assumed fill price for outcome tracking (`(entry_low + entry_high) / 2`), populated by `run_analysis` before insert. `hold_days_min` / `hold_days_max` come from the synthesizer's "5-8 days" output. `hold_days` is kept as a backward-compat alias equal to `hold_days_max`.

```sql
CREATE TABLE recommendations (
    id                   SERIAL PRIMARY KEY,
    weekly_run_id        INTEGER REFERENCES weekly_runs(id),       -- NULL for on-demand
    symbol               VARCHAR(20) NOT NULL,
    exchange             VARCHAR(10) DEFAULT 'NSE',
    recommendation       recommendation_verdict NOT NULL,
    confidence           DOUBLE PRECISION,                          -- 0–10
    entry_low            DOUBLE PRECISION,
    entry_high           DOUBLE PRECISION,
    entry_mid            NUMERIC(12, 2),                            -- (entry_low + entry_high) / 2; assumed fill
    target1              DOUBLE PRECISION,
    target2              DOUBLE PRECISION,
    stop_loss            DOUBLE PRECISION,
    rr_ratio             DOUBLE PRECISION,
    hold_days            INTEGER,                                   -- backward-compat alias = hold_days_max
    hold_days_min        INTEGER,                                   -- e.g. 5  (from "5-8 days")
    hold_days_max        INTEGER,                                   -- e.g. 8  (from "5-8 days")
    strategy_used        VARCHAR(200),
    technical_score      DOUBLE PRECISION,
    sentiment_score      DOUBLE PRECISION,
    smart_money_score    DOUBLE PRECISION,
    reasoning_text       TEXT,
    is_on_demand         BOOLEAN DEFAULT FALSE,                     -- True for /stock or /analyze
    outcome              outcome_verdict DEFAULT 'PENDING',
    outcome_pct          DOUBLE PRECISION,
    outcome_fill_price   NUMERIC(12, 2),
    outcome_exit_price   NUMERIC(12, 2),
    outcome_exit_date    DATE,
    outcome_tracked_at   TIMESTAMP,
    revalidation_note    VARCHAR(200),                              -- set by Monday revalidation job
    revalidated_at       TIMESTAMP,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_recommendations_run     ON recommendations (weekly_run_id);
CREATE INDEX idx_recommendations_symbol  ON recommendations (symbol);
CREATE INDEX idx_recommendations_outcome ON recommendations (outcome);
```

```python
class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True)
    weekly_run_id = Column(Integer, ForeignKey("weekly_runs.id"), nullable=True)  # NULL for on-demand
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(10), default="NSE")
    recommendation = Column(SAEnum(RecommendationVerdict), nullable=False)
    confidence = Column(Float)                                  # 0–10
    entry_low = Column(Float)
    entry_high = Column(Float)
    entry_mid = Column(Numeric(12, 2))                          # (entry_low + entry_high) / 2; assumed fill
    target1 = Column(Float)
    target2 = Column(Float)
    stop_loss = Column(Float)
    rr_ratio = Column(Float)
    hold_days = Column(Integer)                                 # backward-compat alias = hold_days_max
    hold_days_min = Column(Integer)                             # e.g. 5  (from "5-8 days")
    hold_days_max = Column(Integer)                             # e.g. 8  (from "5-8 days")
    strategy_used = Column(String(200))
    technical_score = Column(Float)
    sentiment_score = Column(Float)
    smart_money_score = Column(Float)
    reasoning_text = Column(Text)
    is_on_demand = Column(Boolean, default=False)               # True if triggered via /stock or API
    outcome = Column(SAEnum(OutcomeVerdict), default=OutcomeVerdict.PENDING, index=True)
    outcome_pct = Column(Float, nullable=True)
    outcome_fill_price = Column(Numeric(12, 2), nullable=True)
    outcome_exit_price = Column(Numeric(12, 2), nullable=True)
    outcome_exit_date = Column(Date, nullable=True)
    outcome_tracked_at = Column(DateTime, nullable=True)
    revalidation_note = Column(String(200), nullable=True)      # set by Monday revalidation job
    revalidated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    weekly_run = relationship("WeeklyRun", back_populates="recommendations")
    paper_trades = relationship("PaperTrade", back_populates="recommendation")
```

---

## Table: `mock_portfolios`

Strategy-bucket containers for paper trades.

```sql
CREATE TABLE mock_portfolios (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,                -- e.g. 'aggressive_momentum'
    initial_capital  DOUBLE PRECISION NOT NULL,                   -- e.g. 100000.0
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

```python
class MockPortfolio(Base):
    __tablename__ = "mock_portfolios"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)     # e.g. 'aggressive_momentum'
    initial_capital = Column(Float, nullable=False)             # e.g. 100000.0
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trades = relationship("PaperTrade", back_populates="portfolio")

    @property
    def current_cash(self):
        closed_pnl = sum(t.realised_pnl or 0 for t in self.trades if t.status == TradeStatus.CLOSED)
        invested = sum(t.capital_used for t in self.trades if t.status == TradeStatus.OPEN)
        return self.initial_capital + closed_pnl - invested

    @property
    def total_realised_pnl(self):
        return sum(t.realised_pnl or 0 for t in self.trades if t.status == TradeStatus.CLOSED)

    @property
    def win_rate(self):
        closed = [t for t in self.trades if t.status == TradeStatus.CLOSED]
        if not closed:
            return 0.0
        wins = [t for t in closed if (t.realised_pnl or 0) > 0]
        return len(wins) / len(closed) * 100
```

---

## Table: `paper_trades`

User-driven simulated trades. Inserted on `/confirm` after `/buy`; updated on `/sell` or auto-exit. Status moves OPEN → CLOSED.

```sql
CREATE TABLE paper_trades (
    id                        SERIAL PRIMARY KEY,
    portfolio_id              INTEGER NOT NULL REFERENCES mock_portfolios(id),
    linked_recommendation_id  INTEGER REFERENCES recommendations(id),
    symbol                    VARCHAR(20) NOT NULL,
    direction                 trade_direction DEFAULT 'LONG',
    entry_price               DOUBLE PRECISION NOT NULL,
    entry_date                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shares                    INTEGER NOT NULL,
    capital_used              DOUBLE PRECISION NOT NULL,                  -- entry_price * shares
    exit_price                DOUBLE PRECISION,
    exit_date                 TIMESTAMP,
    realised_pnl              DOUBLE PRECISION,                           -- (exit - entry) * shares
    realised_pnl_pct          DOUBLE PRECISION,                           -- pnl / capital_used * 100
    strategy_used             VARCHAR(200),
    status                    trade_status DEFAULT 'OPEN',
    exit_reason               trade_exit_reason,
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_paper_trades_portfolio ON paper_trades (portfolio_id);
CREATE INDEX idx_paper_trades_status    ON paper_trades (status);
```

```python
class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("mock_portfolios.id"), nullable=False, index=True)
    linked_recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=True)
    symbol = Column(String(20), nullable=False)
    direction = Column(SAEnum(TradeDirection), default=TradeDirection.LONG)
    entry_price = Column(Float, nullable=False)
    entry_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    shares = Column(Integer, nullable=False)
    capital_used = Column(Float, nullable=False)                # entry_price * shares
    exit_price = Column(Float, nullable=True)
    exit_date = Column(DateTime, nullable=True)
    realised_pnl = Column(Float, nullable=True)                 # (exit - entry) * shares
    realised_pnl_pct = Column(Float, nullable=True)             # pnl / capital_used * 100
    strategy_used = Column(String(200), nullable=True)
    status = Column(SAEnum(TradeStatus), default=TradeStatus.OPEN, index=True)
    exit_reason = Column(SAEnum(TradeExitReason), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("MockPortfolio", back_populates="trades")
    recommendation = relationship("Recommendation", back_populates="paper_trades")
```

---

## Table: `watchlist`

User-curated symbols polled by the news monitor.

```sql
CREATE TABLE watchlist (
    id        SERIAL PRIMARY KEY,
    symbol    VARCHAR(20) NOT NULL UNIQUE,
    exchange  VARCHAR(10) DEFAULT 'NSE',
    notes     TEXT,
    added_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

```python
class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True)
    exchange = Column(String(10), default="NSE")
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
```

---

## Table: `news_events`

Material headlines that survive the prefilter and pass the LLM classifier. Drives Telegram alerts.

```sql
CREATE TABLE news_events (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(20) NOT NULL,
    headline      TEXT NOT NULL,
    source        VARCHAR(100),
    published_at  TIMESTAMP,
    sentiment     VARCHAR(20),                      -- 'positive' | 'negative' | 'neutral'
    is_material   BOOLEAN DEFAULT FALSE,
    alert_sent    BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_news_events_symbol_at ON news_events (symbol, published_at DESC);
```

```python
class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    headline = Column(Text, nullable=False)
    source = Column(String(100))
    published_at = Column(DateTime)
    sentiment = Column(String(20))                              # 'positive' / 'negative' / 'neutral'
    is_material = Column(Boolean, default=False)                # True = triggers alert
    alert_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## Table: `rejected_headlines`

Audit log of headlines that were dropped by the keyword prefilter or stoplist before reaching the LLM. Powers the Dashboard "Rejected Headlines (last 7d)" panel and feeds keyword-promotion decisions. Cleanup job (`rejected_headlines_cleanup`) trims rows older than 30 days nightly.

```sql
CREATE TABLE rejected_headlines (
    id             SERIAL PRIMARY KEY,
    symbol         VARCHAR(20),
    headline       TEXT NOT NULL,
    source         VARCHAR(50),
    published_at   TIMESTAMP,
    filter_status  VARCHAR(20),                                 -- 'stoplist' | 'no_keyword'
    rejected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_rejected_symbol_at ON rejected_headlines (symbol, rejected_at DESC);
```

```python
class RejectedHeadline(Base):
    __tablename__ = "rejected_headlines"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), index=True)
    headline = Column(Text, nullable=False)
    source = Column(String(50))
    published_at = Column(DateTime)
    filter_status = Column(String(20))                          # 'stoplist' | 'no_keyword'
    rejected_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_rejected_symbol_at", "symbol", "rejected_at"),
    )
```

---

## Table: `backtest_results`

One row per bundle per weekly backtest. Drives strategy-weighting in `MarketRegimeAgent`.

```sql
CREATE TABLE backtest_results (
    id                SERIAL PRIMARY KEY,
    bundle_name       VARCHAR(50) NOT NULL,                     -- 'trend' / 'reversal' / 'breakout' / 'smc' / 'composite'
    run_date          DATE NOT NULL,
    win_rate          DOUBLE PRECISION,                         -- 0.0 to 1.0
    avg_return_pct    DOUBLE PRECISION,                         -- average % return per trade
    max_drawdown_pct  DOUBLE PRECISION,                         -- peak-to-trough drawdown
    sharpe_ratio      DOUBLE PRECISION,
    total_trades      INTEGER,
    weight_assigned   DOUBLE PRECISION,                         -- 0.0 to 1.0 (sum = 1.0 across bundles)
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_backtest_results_bundle_date ON backtest_results (bundle_name, run_date DESC);
```

```python
class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True)
    bundle_name = Column(String(50), nullable=False)            # 'trend' / 'reversal' / 'breakout' / 'smc' / 'composite'
    run_date = Column(Date, nullable=False)
    win_rate = Column(Float)                                    # 0.0 to 1.0
    avg_return_pct = Column(Float)                              # average % return per trade
    max_drawdown_pct = Column(Float)                            # peak-to-trough drawdown
    sharpe_ratio = Column(Float)
    total_trades = Column(Integer)
    weight_assigned = Column(Float)                             # 0.0 to 1.0 (sum = 1.0 across bundles)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_backtest_results_bundle_date", "bundle_name", "run_date"),
    )
```

---

## `src/plutus/db/session.py`

Standard SQLAlchemy engine + session factory. `DATABASE_URL` is read from `plutus.config.settings`.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from plutus.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in plutus.db.models."""
    pass


def get_db():
    """FastAPI dependency: yields a session and closes it on request teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## `src/plutus/db/init_db.py`

Imports `plutus.db.models` so every `Base` subclass is registered, then creates all tables. Idempotent — safe to run on a fresh DB or an existing one.

```python
from plutus.db.session import Base, engine
from plutus.db import models  # noqa: F401 — import all models so they register with Base


def init():
    Base.metadata.create_all(bind=engine)
    print("All tables created.")


if __name__ == "__main__":
    init()
```

---

## Key Database Queries (Reference for Other Modules)

### Get latest weekly recommendations

```python
from plutus.db.session import SessionLocal
from plutus.db.models import WeeklyRun, Recommendation, RecommendationVerdict


def get_latest_recommendations(limit: int = 20):
    with SessionLocal() as db:
        latest_run = db.query(WeeklyRun).order_by(WeeklyRun.run_date.desc()).first()
        if not latest_run:
            return []
        return (
            db.query(Recommendation)
            .filter(Recommendation.weekly_run_id == latest_run.id)
            .filter(Recommendation.recommendation.in_([
                RecommendationVerdict.BUY, RecommendationVerdict.WATCH,
            ]))
            .order_by(Recommendation.confidence.desc())
            .limit(limit)
            .all()
        )
```

### Get portfolio summary

```python
from plutus.db.session import SessionLocal
from plutus.db.models import MockPortfolio, TradeStatus


def get_portfolio_summary(portfolio_name: str):
    with SessionLocal() as db:
        portfolio = db.query(MockPortfolio).filter(MockPortfolio.name == portfolio_name).first()
        if not portfolio:
            return None
        open_trades = [t for t in portfolio.trades if t.status == TradeStatus.OPEN]
        return {
            "name": portfolio.name,
            "initial_capital": portfolio.initial_capital,
            "current_cash": portfolio.current_cash,
            "realised_pnl": portfolio.total_realised_pnl,
            "win_rate": portfolio.win_rate,
            "open_positions": len(open_trades),
        }
```

### Track recommendation outcomes (run daily after market close)

The full algorithm — including IST trading-day math, entry-mid fill price, and the conservative "stop wins on same-day collision" rule — lives in `12_scheduler.md` § `outcome_tracker`. The skeleton below shows only the column wiring it depends on.

```python
from datetime import datetime
import pytz

from plutus.db.session import SessionLocal
from plutus.db.models import Recommendation, OutcomeVerdict
from plutus.data.ohlcv import fetch_ohlcv
from plutus.data.calendar import nse_trading_days_between

IST = pytz.timezone("Asia/Kolkata")


def track_outcomes():
    today_ist = datetime.now(IST).date()
    with SessionLocal() as db:
        pending = (
            db.query(Recommendation)
            .filter(Recommendation.outcome.in_([None, OutcomeVerdict.PENDING]))
            .all()
        )

        for rec in pending:
            created_ist = rec.created_at.astimezone(IST).date()
            elapsed = nse_trading_days_between(created_ist, today_ist)
            if elapsed < (rec.hold_days_min or 5):
                continue

            df = fetch_ohlcv(rec.symbol, days=elapsed + 5)
            df = df[df.index.date > created_ist]
            if df.empty:
                continue

            fill = float(rec.entry_mid or rec.entry_high)
            stop = float(rec.stop_loss)
            t1 = float(rec.target1)
            t2 = float(rec.target2) if rec.target2 else None

            outcome = None
            exit_price = None
            exit_date = None
            for idx, row in df.iterrows():
                hit_t2 = t2 is not None and row.High >= t2
                hit_t1 = row.High >= t1
                hit_stop = row.Low <= stop
                # Conservative ambiguity rule: stop wins on same-day collision.
                if hit_stop and (hit_t1 or hit_t2):
                    outcome, exit_price = OutcomeVerdict.STOPPED, stop
                elif hit_t2:
                    outcome, exit_price = OutcomeVerdict.HIT_T2, t2
                elif hit_t1:
                    outcome, exit_price = OutcomeVerdict.HIT_T1, t1
                elif hit_stop:
                    outcome, exit_price = OutcomeVerdict.STOPPED, stop
                if outcome:
                    exit_date = idx.date()
                    break

            if not outcome:
                if elapsed >= (rec.hold_days_max or 10):
                    outcome = OutcomeVerdict.EXPIRED
                    exit_price = float(df.iloc[-1].Close)
                    exit_date = df.index[-1].date()
                else:
                    continue

            rec.outcome = outcome
            rec.outcome_pct = (exit_price - fill) / fill * 100
            rec.outcome_fill_price = fill
            rec.outcome_exit_price = exit_price
            rec.outcome_exit_date = exit_date
            rec.outcome_tracked_at = datetime.utcnow()

        db.commit()
```
