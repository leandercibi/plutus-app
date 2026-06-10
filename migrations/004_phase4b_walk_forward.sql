-- migrations/004_phase4b_walk_forward.sql
-- Phase 4b: Walk-forward evaluation runs

CREATE TABLE IF NOT EXISTS walk_forward_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    overfit_flag BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wfr_symbol_bundle_date
    ON walk_forward_runs (symbol, bundle_name, run_date);
