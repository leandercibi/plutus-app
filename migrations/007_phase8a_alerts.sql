-- Migration 007: Phase 8a — position-aware alert model
-- Run once: psql $DATABASE_URL -f migrations/007_phase8a_alerts.sql

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_type') THEN
        CREATE TYPE alert_type AS ENUM (
            'PRE_SL_WARNING', 'TARGET1_HIT', 'TARGET2_HIT', 'TREND_INVALIDATED'
        );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS alerts (
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

CREATE INDEX IF NOT EXISTS idx_alerts_trade_type_time ON alerts (trade_id, alert_type, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_portfolio_time  ON alerts (portfolio_id, triggered_at DESC);
