-- Migration 011: drop current_cash from mock_portfolios
-- current_cash is now a computed Python property (initial_capital - open_capital_used + closed_pnl)
-- The column is no longer written by the ORM; drop it to keep schema clean.

ALTER TABLE mock_portfolios DROP COLUMN IF EXISTS current_cash;
