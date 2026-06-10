-- migrations/005_phase4_5_tuning.sql
-- Phase 4.5: Self-finetuning loop tables

CREATE TABLE IF NOT EXISTS tuning_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    report_date DATE NOT NULL,
    dimension VARCHAR(50) NOT NULL,
    dimension_value VARCHAR(50) NOT NULL,
    current_win_rate FLOAT NOT NULL,
    target_win_rate FLOAT NOT NULL,
    n_trades INTEGER NOT NULL,
    suggestion_text TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    applied_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_ts_dimension_date
    ON tuning_suggestions (dimension, report_date);

CREATE TABLE IF NOT EXISTS tuning_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL REFERENCES tuning_suggestions(id),
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    dimension VARCHAR(50) NOT NULL,
    dimension_value VARCHAR(50) NOT NULL,
    change_description TEXT NOT NULL,
    win_rate_before FLOAT,
    win_rate_after FLOAT,
    rollback_after DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_th_suggestion
    ON tuning_history (suggestion_id);
