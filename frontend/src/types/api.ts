// Regime
export interface RegimeSnapshot {
  as_of_date: string
  label: 'BULL' | 'BEAR' | 'SIDEWAYS'
  nifty_close: string
  pct_above_50dma: number
  pct_above_200dma: number
  advance_decline: number
  india_vix: number
  fii_flow_inr: string
  dii_flow_inr: string
  breadth_confirmed_flip: boolean
}

// Portfolio
export interface PositionSnapshot {
  symbol: string
  mode: string
  qty: number
  avg_cost: number
  current_price: number
  pnl: number
  pnl_pct: number
  stop_loss: number | null
  sl_distance_pct: number | null
  // Populated for swing lots only (one snapshot row per SwingTrade). Enables the
  // Positions page to aggregate rows by symbol and dispatch per-lot Exit / partial
  // sell actions to the right specific trade.
  trade_id: number | null
  opened_at: string | null
}

export interface PortfolioSnapshot {
  positions: PositionSnapshot[]
  total_invested: number
  total_current: number
  total_pnl: number
  total_pnl_pct: number
  // Live realised P/L across closed swing trades — sourced from actual fills
  // on every request. Replaces the old weekly-postmortem read that only
  // refreshed on Sundays.
  total_realized_pnl: number
  total_realized_pct: number
  n_closed_trades: number
  checked_at: string
}

// Pillar breakdown from swing signals
export interface PillarBreakdown {
  technical: number
  expectancy: number
  flow: number
  regime_fit: number
  fundamentals: number
  sentiment: number
}

// Swing Signal
export interface SwingSignal {
  id: number
  run_id: string
  symbol: string
  bundle: string
  score: number
  label: string
  entry: string
  stop_loss: string
  target_1: string
  target_2: string
  expectancy_R: number
  drawn_rr: number
  regime_at_signal: string
  pillar_breakdown: PillarBreakdown
  counterfactual: string | null
  calibration_band: string
  created_at: string
}

// Swing Trade (open position from /swing/positions)
export interface SwingTrade {
  id: number
  signal_id: number
  symbol: string
  bundle: string
  state: string
  opened_at: string
  closed_at: string | null
  qty: number
  risk_R: number
  exit_reason: string | null
  realized_R: number | null
  mfe_R: number | null
  mae_R: number | null
}

// Accumulation Candidate
export interface AccumulationCandidate {
  id: number
  run_id: string
  symbol: string
  score: number
  rs_30: number
  rs_90: number
  rs_180: number
  cagr_eps_3y: number | null
  valuation_pillar_pct: number
  thesis_text: string
  hard_avoid_active: boolean
  created_at: string
}

// Accumulation Position
export interface AccumulationPosition {
  id: number
  symbol: string
  state: string
  avg_cost: string
  qty_total: number
  opened_at: string
  last_thesis_check_at: string
}

// Calibration Row
export interface CalibrationRow {
  bucket: string
  regime: string
  n_closed: number
  win_rate: number
  expectancy_R: number
  ci_low_R: number
  ci_high_R: number
  sprt_state: string
  confidence_band: string
  last_updated: string
}

// Weekly postmortem (portfolio vs benchmarks)
export interface Postmortem {
  week_ending: string
  swing_return_pct: number
  nifty_return_pct: number
  regime_switched_return_pct: number
  random_baseline_return_pct: number
  n_swing_trades_closed: number
  drawdown_pct: number
  report_md_path: string | null
}

// Signal-stock news (Marketaux)
export interface NewsItem {
  symbol: string
  title: string
  snippet: string
  url: string
  source: string
  published_at: string
  sentiment_score: number | null
  sentiment: 'positive' | 'negative' | 'neutral'
  sector: string | null
}

export interface SignalNews {
  items: NewsItem[]
  symbols: string[]
  sectors: string[]
  fetched_at: string
  cached: boolean
  available: boolean
}

// AI Summary
export interface AiSummary {
  kind: 'weekly_pipeline' | 'daily_holdings'
  cache_key: string
  content: string
  model: string
  created_at: string
  cached: boolean
  available: boolean
}

// Run Log
export interface RunLogRow {
  run_id: string
  job_name: string
  started_at: string
  ended_at: string | null
  status: string | null
  details_json: Record<string, unknown> | null
}

// Chart data — bars come back with `date` (ISO string) + OHLCV + indicator fields inline
export interface ChartBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  dma20?: number
  dma50?: number
  dma200?: number
  macd?: number
  macd_signal?: number
  macd_hist?: number
  bb_upper?: number
  bb_lower?: number
  bb_mid?: number
  golden_cross_20_50?: boolean
}

export interface ChartResponse {
  symbol: string
  latest_price: number
  latest_change_pct: number
  bars: ChartBar[]
  signal_marker?: {
    date: string
    entry?: number
    stop_loss?: number
    target_1?: number
    target_2?: number
  } | null
}

export interface BacktestTrade {
  entry_date: string
  exit_date: string
  hold_days: number
  realized_R: number
}

export interface BacktestRequest {
  bundle: string
  symbol: string
  lookback_days: number
  use_cost_model: boolean
  use_fill_policy: boolean
}

export interface BacktestResult {
  bundle: string
  symbol: string
  start: string
  end: string
  n_trades: number
  win_rate: number
  expectancy_R: number
  sum_R: number
  avg_hold_days: number
  fills_before_signal: number
  cost_model_on: boolean
  fill_policy_on: boolean
  trades: BacktestTrade[]
}
