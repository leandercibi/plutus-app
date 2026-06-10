-- Plutus database schema (reference / audit artifact).
-- Must stay 1-to-1 with src/plutus/db/models.py. See specs/04_database.md.

-- ---------------------------------------------------------------------------
-- Enum types
-- ---------------------------------------------------------------------------

CREATE TYPE recommendation_verdict AS ENUM ('BUY', 'SELL', 'HOLD', 'WATCH', 'AVOID');
CREATE TYPE trade_direction       AS ENUM ('LONG', 'SHORT');
CREATE TYPE trade_status          AS ENUM ('OPEN', 'CLOSED');
CREATE TYPE trade_exit_reason     AS ENUM ('TARGET1', 'TARGET2', 'STOP', 'MANUAL', 'SIGNAL', 'EXPIRED');
CREATE TYPE outcome_verdict       AS ENUM ('HIT_T1', 'HIT_T2', 'STOPPED', 'EXPIRED', 'PENDING');

-- ---------------------------------------------------------------------------
-- weekly_runs
-- ---------------------------------------------------------------------------

CREATE TABLE weekly_runs (
    id                   SERIAL PRIMARY KEY,
    run_date             DATE NOT NULL,
    run_type             VARCHAR(20) NOT NULL DEFAULT 'scheduled',  -- 'scheduled' | 'manual'
    market_regime        VARCHAR(50),                      -- 'BULLISH' | 'BEARISH' | 'SIDEWAYS'
    nifty_trend          VARCHAR(50),                      -- 'ABOVE_EMA50' | 'BELOW_EMA50'
    strategy_selected    VARCHAR(200),                     -- JSON string of bundle names + weights
    stocks_screened      INTEGER,
    stocks_analysed      INTEGER,
    total_buy_signals    INTEGER DEFAULT 0,
    total_watch_signals  INTEGER DEFAULT 0,
    report_md_path       VARCHAR(500),
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at         TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- recommendations
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- mock_portfolios
-- ---------------------------------------------------------------------------

CREATE TABLE mock_portfolios (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,                -- e.g. 'aggressive_momentum'
    initial_capital  DOUBLE PRECISION NOT NULL,                   -- e.g. 100000.0
    current_cash     DOUBLE PRECISION,                            -- deprecated: now computed from trades
    notes            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- paper_trades
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- watchlist
-- ---------------------------------------------------------------------------

CREATE TABLE watchlist (
    id        SERIAL PRIMARY KEY,
    symbol    VARCHAR(20) NOT NULL UNIQUE,
    exchange  VARCHAR(10) DEFAULT 'NSE',
    notes     TEXT,
    added_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- news_events
-- ---------------------------------------------------------------------------

CREATE TABLE news_events (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(20) NOT NULL,
    headline      TEXT NOT NULL,
    source        VARCHAR(100),
    published_at  TIMESTAMP,
    sentiment     VARCHAR(20),                      -- 'positive' | 'negative' | 'neutral'
    sentiment_label VARCHAR(30),                    -- human-readable: 'strongly positive' etc.
    material_event_type VARCHAR(50),                -- 'earnings' | 'regulatory' | 'promoter' etc.
    is_material   BOOLEAN DEFAULT FALSE,
    alert_sent    BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_news_events_symbol_at ON news_events (symbol, published_at DESC);

-- ---------------------------------------------------------------------------
-- rejected_headlines
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- backtest_results
-- ---------------------------------------------------------------------------

CREATE TABLE backtest_results (
    id                SERIAL PRIMARY KEY,
    weekly_run_id     INTEGER REFERENCES weekly_runs(id),
    symbol            VARCHAR(20) NOT NULL,
    bundle_name       VARCHAR(50) NOT NULL,                     -- 'trend' / 'reversal' / 'breakout' / 'smc' / 'composite'
    run_date          DATE NOT NULL,
    win_rate          DOUBLE PRECISION,                         -- 0.0 to 1.0
    avg_return_pct    DOUBLE PRECISION,                         -- average % return per trade
    max_drawdown_pct  DOUBLE PRECISION,                         -- peak-to-trough drawdown
    sharpe_ratio      DOUBLE PRECISION,
    total_trades      INTEGER,
    weight_assigned   DOUBLE PRECISION,                         -- 0.0 to 1.0 (sum = 1.0 across bundles)
    equity_curve_json TEXT,                                     -- JSON: [{date, equity}, ...]
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_backtest_results_bundle_date ON backtest_results (bundle_name, run_date DESC);

-- ---------------------------------------------------------------------------
-- alerts  (Phase 8a: position-aware alert monitor)
-- ---------------------------------------------------------------------------

CREATE TYPE alert_type AS ENUM ('PRE_SL_WARNING', 'TARGET1_HIT', 'TARGET2_HIT', 'TREND_INVALIDATED');

CREATE TABLE alerts (
    id              SERIAL PRIMARY KEY,
    trade_id        INTEGER NOT NULL REFERENCES paper_trades(id),
    portfolio_id    INTEGER NOT NULL REFERENCES mock_portfolios(id),
    symbol          VARCHAR(20) NOT NULL,
    alert_type      alert_type NOT NULL,
    triggered_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message         TEXT NOT NULL,
    channels_sent   JSONB DEFAULT '[]',
    acknowledged    BOOLEAN DEFAULT FALSE,
    ltp_at_trigger  DOUBLE PRECISION,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_alerts_trade_type_time ON alerts (trade_id, alert_type, triggered_at DESC);
CREATE INDEX idx_alerts_portfolio_time  ON alerts (portfolio_id, triggered_at DESC);
