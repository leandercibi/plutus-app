import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type {
  RegimeSnapshot, PortfolioSnapshot, SwingSignal, SwingTrade,
  AccumulationCandidate, AccumulationPosition, CalibrationRow,
  RunLogRow, ChartResponse, BacktestRequest, BacktestResult, AiSummary, SignalNews,
  Postmortem,
} from '../types/api'

// ── Auth ─────────────────────────────────────────────
export function useVerifyToken(token: string) {
  return useQuery({
    queryKey: ['auth', token],
    queryFn: () =>
      apiClient.post<{ ok: boolean }>('/auth/verify', null, {
        headers: { Authorization: `Bearer ${token}` },
      }).then(r => r.data),
    enabled: !!token,
    retry: false,
  })
}

// ── Shared ───────────────────────────────────────────
export function useRegime() {
  return useQuery({
    queryKey: ['regime'],
    queryFn: () => apiClient.get<RegimeSnapshot>('/shared/regime').then(r => r.data),
    refetchInterval: 60_000,
  })
}

export function usePortfolioSnapshot() {
  return useQuery({
    queryKey: ['portfolio-snapshot'],
    queryFn: () => apiClient.get<PortfolioSnapshot>('/shared/portfolio-snapshot').then(r => r.data),
    refetchInterval: 180_000, // swing trading — backend caches prices for 3min, no need to poll faster
  })
}

export function useLTP(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ['ltp', symbol],
    queryFn: () =>
      apiClient.get<{ symbol: string; price: number }>(`/shared/ltp/${symbol}`)
        .then(r => r.data.price)
        .catch(() => null),   // 404 / unavailable → null
    enabled: !!symbol && enabled,
    staleTime: 180_000,
    retry: false,
  })
}

export function useChart(symbol: string, signalId?: number, days = 90, enabled = true) {
  return useQuery({
    queryKey: ['chart', symbol, signalId, days],
    queryFn: () =>
      apiClient.get<ChartResponse>(`/shared/chart/${symbol}`, {
        params: { signal_id: signalId, days },
      }).then(r => r.data),
    enabled: !!symbol && enabled,
    staleTime: 5 * 60_000,
  })
}

export function useNseSymbols() {
  return useQuery({
    queryKey: ['nse-symbols'],
    queryFn: () => apiClient.get<string[]>('/shared/nse-symbols').then(r => r.data),
    staleTime: 24 * 60 * 60_000, // full NSE list changes rarely intraday
  })
}

export function useQuickScore(symbol: string, enabled = true) {
  return useQuery({
    queryKey: ['quick-score', symbol],
    queryFn: () => apiClient.get<SwingSignal>(`/shared/quick-score/${symbol}`).then(r => r.data),
    enabled: !!symbol && enabled,
    retry: false,
    staleTime: 60_000,
  })
}

export function useRunLog(limit = 10) {
  return useQuery({
    queryKey: ['run-log', limit],
    queryFn: () => apiClient.get<RunLogRow[]>('/shared/run-log', { params: { limit } }).then(r => r.data),
  })
}

export function usePostmortem() {
  return useQuery({
    queryKey: ['postmortem'],
    queryFn: () => apiClient.get<Postmortem>('/swing/postmortem/latest').then(r => r.data).catch(() => null),
    retry: false,
  })
}

export function useCalibration() {
  return useQuery({
    queryKey: ['calibration'],
    queryFn: () => apiClient.get<CalibrationRow[]>('/shared/calibration').then(r => r.data),
  })
}

// ── AI summaries ─────────────────────────────────────
// Summaries are cached server-side (per pipeline run / per day), so the GET is
// cheap and won't re-bill the LLM. `staleTime` is long; use the refresh
// mutation (force=true) to regenerate on demand.
export function useWeeklyPipelineSummary() {
  return useQuery({
    queryKey: ['ai', 'weekly-summary'],
    queryFn: () => apiClient.get<AiSummary>('/ai/weekly-summary').then(r => r.data),
    staleTime: 30 * 60_000,
    retry: false,
  })
}

export function useDailyHoldingsSummary() {
  return useQuery({
    queryKey: ['ai', 'daily-summary'],
    queryFn: () => apiClient.get<AiSummary>('/ai/daily-summary').then(r => r.data),
    staleTime: 30 * 60_000,
    retry: false,
  })
}

// Live news for the current signal-list stocks. Server caches ~15 min, so this
// is safe to poll; refresh mutation forces a refetch.
export function useSignalNews() {
  return useQuery({
    queryKey: ['ai', 'signal-news'],
    queryFn: () => apiClient.get<SignalNews>('/ai/signal-news').then(r => r.data),
    staleTime: 10 * 60_000,
    refetchInterval: 15 * 60_000,
    retry: false,
  })
}

export function useRefreshSignalNews() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient.get<SignalNews>('/ai/signal-news', { params: { force: true }, timeout: 30_000 })
        .then(r => r.data),
    onSuccess: (data) => qc.setQueryData(['ai', 'signal-news'], data),
  })
}

export function useRefreshAiSummary(kind: 'weekly' | 'daily') {
  const qc = useQueryClient()
  const path = kind === 'weekly' ? '/ai/weekly-summary' : '/ai/daily-summary'
  const key = kind === 'weekly' ? 'weekly-summary' : 'daily-summary'
  return useMutation({
    mutationFn: () =>
      apiClient.get<AiSummary>(path, { params: { force: true }, timeout: 60_000 })
        .then(r => r.data),
    onSuccess: (data) => qc.setQueryData(['ai', key], data),
  })
}

// ── Run triggers ─────────────────────────────────────
export function useTriggerSundayRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/shared/runs/sunday').then(r => r.data),
    onSuccess: () => {
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['run-log'] })
        qc.invalidateQueries({ queryKey: ['signals'] })
        qc.invalidateQueries({ queryKey: ['regime'] })
      }, 3000)
    },
  })
}

export function useTriggerMondayRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/shared/runs/monday-revalidation').then(r => r.data),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['run-log'] }), 3000)
    },
  })
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (req: BacktestRequest) =>
      apiClient.post<BacktestResult>('/shared/backtest', req, { timeout: 120_000 })
        .then(r => r.data),
  })
}

export function useTriggerMidweekRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/shared/runs/midweek-mini').then(r => r.data),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['run-log'] }), 3000)
    },
  })
}

// ── Swing ────────────────────────────────────────────
export function useSignals() {
  return useQuery({
    queryKey: ['signals'],
    queryFn: () =>
      apiClient.get<SwingSignal[]>('/swing/signals', {
        params: { latest_run: true, dedup: true },
      }).then(r => r.data),
  })
}

export function useSwingPositions() {
  return useQuery({
    queryKey: ['swing-positions'],
    queryFn: () => apiClient.get<SwingTrade[]>('/swing/positions').then(r => r.data),
    refetchInterval: 60_000,
  })
}

export function useEnterSignal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ signalId, side, qty, price }: { signalId: number; side: 'BUY' | 'SELL'; qty: number; price: number }) =>
      apiClient.post(`/swing/signals/${signalId}/enter`, { side, qty, price }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['swing-positions'] })
      qc.invalidateQueries({ queryKey: ['portfolio-snapshot'] })
    },
  })
}

export function useExitTrade() {
  const qc = useQueryClient()
  return useMutation({
    // qty omitted → full close (backend closes trade, sets state = CLOSED_WIN/LOSS).
    // qty < trade.qty → partial exit (backend logs SELL fill, decrements qty, stays OPEN).
    mutationFn: ({ tradeId, reason, qty }: { tradeId: number; reason: string; qty?: number }) =>
      apiClient.post(`/swing/trades/${tradeId}/exit/manual`,
        qty !== undefined ? { reason, qty } : { reason }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['swing-positions'] })
      qc.invalidateQueries({ queryKey: ['portfolio-snapshot'] })
    },
  })
}

// ── Accumulation ──────────────────────────────────────
export function useCandidates() {
  return useQuery({
    queryKey: ['candidates'],
    queryFn: () => apiClient.get<AccumulationCandidate[]>('/accumulation/candidates').then(r => r.data),
  })
}

export function useStartAccumulationPosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ symbol, price, qty, note = '' }: { symbol: string; price: number; qty: number; note?: string }) =>
      apiClient.post('/accumulation/positions', { symbol, price, qty, note }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accumulation-positions'] })
      qc.invalidateQueries({ queryKey: ['portfolio-snapshot'] })
    },
  })
}

// Adds a subsequent tranche (2..5) to an already-open accumulation position.
// Backend enforces max-5 tranches and 409s on closed positions.
export function useAddTranche() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ positionId, price, qty, note = '' }: { positionId: number; price: number; qty: number; note?: string }) =>
      apiClient.post(`/accumulation/positions/${positionId}/tranches`, { price, qty, note }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accumulation-positions'] })
      qc.invalidateQueries({ queryKey: ['portfolio-snapshot'] })
    },
  })
}

export function useAccumulationPositions() {
  return useQuery({
    queryKey: ['accumulation-positions'],
    queryFn: () => apiClient.get<AccumulationPosition[]>('/accumulation/positions').then(r => r.data),
    refetchInterval: 60_000,
  })
}

export function usePauseAccumulationPosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`/accumulation/positions/${id}/pause`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accumulation-positions'] }),
  })
}

export function useResumeAccumulationPosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`/accumulation/positions/${id}/resume`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accumulation-positions'] }),
  })
}

export function useExitAccumulationPosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, price, qty, reason = 'manual' }: { id: number; price: number; qty: number; reason?: string }) =>
      apiClient.post(`/accumulation/positions/${id}/exit`, { price, qty, reason }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accumulation-positions'] })
      qc.invalidateQueries({ queryKey: ['portfolio-snapshot'] })
    },
  })
}
