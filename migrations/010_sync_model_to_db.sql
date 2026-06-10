-- Missing tables from SQLAlchemy models

CREATE TABLE IF NOT EXISTS market_regime_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    nifty_trend VARCHAR(20) NOT NULL,
    nifty_slope FLOAT,
    distance_from_ema50_pct FLOAT,
    sector_rs JSON,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_market_regime_snapshots_snapshot_date ON market_regime_snapshots (snapshot_date);

CREATE TYPE outcomeverdict AS ENUM ('HIT_T1','HIT_T2','STOPPED','WRONG_DIRECTION','EXPIRED','PENDING');

CREATE TABLE IF NOT EXISTS trade_outcomes_audit (
    id SERIAL PRIMARY KEY,
    recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
    symbol VARCHAR(20) NOT NULL,
    outcome outcomeverdict NOT NULL,
    outcome_pct FLOAT,
    exit_date DATE,
    mfe_pct FLOAT,
    mae_pct FLOAT,
    trading_days_held INTEGER,
    score_bucket VARCHAR(20),
    bundle_used VARCHAR(200),
    regime_at_signal VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_trade_outcomes_audit_recommendation_id ON trade_outcomes_audit (recommendation_id);
CREATE INDEX IF NOT EXISTS ix_trade_outcomes_audit_symbol ON trade_outcomes_audit (symbol);
CREATE INDEX IF NOT EXISTS ix_trade_outcomes_audit_outcome ON trade_outcomes_audit (outcome);
CREATE INDEX IF NOT EXISTS ix_trade_outcomes_audit_score_bucket ON trade_outcomes_audit (score_bucket);

CREATE TABLE IF NOT EXISTS walk_forward_runs (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    bundle_name VARCHAR(50) NOT NULL,
    run_date DATE NOT NULL,
    window_idx INTEGER NOT NULL,
    is_start DATE NOT NULL,
    is_end DATE NOT NULL,
    oos_start DATE NOT NULL,
    oos_end DATE NOT NULL,
    is_sharpe FLOAT,
    oos_sharpe FLOAT,
    is_trades INTEGER,
    oos_trades INTEGER,
    is_win_rate FLOAT,
    oos_win_rate FLOAT,
    overfit_flag BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_walk_forward_runs_symbol ON walk_forward_runs (symbol);
CREATE INDEX IF NOT EXISTS ix_walk_forward_runs_bundle_name ON walk_forward_runs (bundle_name);
CREATE INDEX IF NOT EXISTS ix_walk_forward_runs_run_date ON walk_forward_runs (run_date);
CREATE INDEX IF NOT EXISTS idx_wfr_symbol_bundle_date ON walk_forward_runs (symbol, bundle_name, run_date);

CREATE TABLE IF NOT EXISTS trading_params (
    id SERIAL PRIMARY KEY,
    param_key VARCHAR(60) NOT NULL UNIQUE,
    value VARCHAR(100) NOT NULL,
    value_type VARCHAR(10) NOT NULL DEFAULT 'float',
    min_allowed FLOAT,
    max_allowed FLOAT,
    label VARCHAR(100),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(50) DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS ix_trading_params_param_key ON trading_params (param_key);

CREATE TABLE IF NOT EXISTS tuning_suggestions (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW(),
    report_date DATE NOT NULL,
    dimension VARCHAR(50) NOT NULL,
    dimension_value VARCHAR(50) NOT NULL,
    current_win_rate FLOAT NOT NULL,
    target_win_rate FLOAT NOT NULL,
    n_trades INTEGER NOT NULL,
    suggestion_text TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    applied_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_tuning_suggestions_report_date ON tuning_suggestions (report_date);
CREATE INDEX IF NOT EXISTS ix_tuning_suggestions_dimension ON tuning_suggestions (dimension);
CREATE INDEX IF NOT EXISTS idx_ts_dimension_date ON tuning_suggestions (dimension, report_date);

CREATE TABLE IF NOT EXISTS tuning_history (
    id SERIAL PRIMARY KEY,
    suggestion_id INTEGER NOT NULL REFERENCES tuning_suggestions(id),
    applied_at TIMESTAMP DEFAULT NOW(),
    dimension VARCHAR(50) NOT NULL,
    dimension_value VARCHAR(50) NOT NULL,
    change_description TEXT NOT NULL,
    win_rate_before FLOAT,
    win_rate_after FLOAT,
    rollback_after TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tuning_history_suggestion_id ON tuning_history (suggestion_id);

CREATE TYPE alerttype AS ENUM ('PRE_SL_WARNING','TARGET1_HIT','TARGET2_HIT','TREND_INVALIDATED');

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES paper_trades(id),
    portfolio_id INTEGER NOT NULL REFERENCES mock_portfolios(id),
    symbol VARCHAR(20) NOT NULL,
    alert_type alerttype NOT NULL,
    triggered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    message TEXT NOT NULL,
    channels_sent JSON DEFAULT '[]',
    acknowledged BOOLEAN DEFAULT FALSE,
    ltp_at_trigger FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_alerts_trade_id ON alerts (trade_id);
CREATE INDEX IF NOT EXISTS ix_alerts_portfolio_id ON alerts (portfolio_id);
