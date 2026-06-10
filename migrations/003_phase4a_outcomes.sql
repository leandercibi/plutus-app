-- Phase 4a: outcome tracker additions

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS mfe_pct REAL;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS mae_pct REAL;

CREATE TABLE IF NOT EXISTS trade_outcomes_audit (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER NOT NULL REFERENCES recommendations(id),
    symbol            VARCHAR(20) NOT NULL,
    outcome           VARCHAR(20) NOT NULL,
    outcome_pct       REAL,
    exit_date         DATE,
    mfe_pct           REAL,
    mae_pct           REAL,
    trading_days_held INTEGER,
    score_bucket      VARCHAR(20),
    bundle_used       VARCHAR(200),
    regime_at_signal  VARCHAR(20),
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_toa_recommendation ON trade_outcomes_audit(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_toa_symbol ON trade_outcomes_audit(symbol);
CREATE INDEX IF NOT EXISTS idx_toa_outcome ON trade_outcomes_audit(outcome);
CREATE INDEX IF NOT EXISTS idx_toa_score_bucket ON trade_outcomes_audit(score_bucket);
