-- migrations/006_phase6_trading_params.sql
-- Phase 6: Editable trading parameters

CREATE TABLE IF NOT EXISTS trading_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_key VARCHAR(60) NOT NULL UNIQUE,
    value VARCHAR(100) NOT NULL,
    value_type VARCHAR(10) NOT NULL DEFAULT 'float',
    min_allowed FLOAT,
    max_allowed FLOAT,
    label VARCHAR(100),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(50) DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_trading_params_key
    ON trading_params (param_key);

-- params_version_id on weekly_runs (safe if column already exists)
-- SQLite: just try ALTER TABLE; ignore "duplicate column" error in scripts
ALTER TABLE weekly_runs ADD COLUMN params_version_id VARCHAR(16);
