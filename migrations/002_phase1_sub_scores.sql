-- Migration 002: add regime_score and rr_score to recommendations

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS regime_score REAL;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS rr_score REAL;
