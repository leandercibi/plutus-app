-- Migration 001: market_regime_snapshots
-- Stores weekly Nifty regime + sector RS snapshots.

CREATE TABLE IF NOT EXISTS market_regime_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date           DATE NOT NULL UNIQUE,
    nifty_trend             VARCHAR(20) NOT NULL,    -- 'BULL' | 'BEAR' | 'SIDEWAYS'
    nifty_slope             REAL,                    -- EMA50 5-day slope fraction
    distance_from_ema50_pct REAL,                    -- (close - ema50) / ema50 * 100
    sector_rs               TEXT,                    -- JSON: {"IT": 1.18, "BANK": 1.05, ...}
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_regime_snapshots_date ON market_regime_snapshots(snapshot_date);
