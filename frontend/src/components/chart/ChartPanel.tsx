import { useState } from 'react'
import { useChart } from '../../api/hooks'
import { Skeleton } from '../ui/Skeleton'
import { ErrorBanner } from '../ui/ErrorBanner'
import { StockChart } from './StockChart'
import type { UseQueryResult } from '@tanstack/react-query'
import type { ChartResponse } from '../../types/api'

export type ChartIndicators = { macd: boolean; bb: boolean; goldenCross: boolean }

export const DEFAULT_CHART_INDICATORS: ChartIndicators = { macd: false, bb: false, goldenCross: false }

/** Shared expand/collapse + data-fetch state for a symbol's chart. Used by both the
 * Signals and Positions pages so the toggle button and chart body stay in sync with
 * whatever layout each page places them in. */
export function useChartPanel(symbol: string, signalId: number | undefined, days: number) {
  const [expanded, setExpanded] = useState(false)
  const chart = useChart(symbol, signalId, days, expanded)
  return { expanded, setExpanded, chart }
}

export function ChartToggleButton({
  expanded,
  onToggle,
  label = 'Chart',
}: {
  expanded: boolean
  onToggle: () => void
  /** Text after the chevron when collapsed. Defaults to "Chart"; Positions passes
   * "Lots" for multi-lot rows since the expanded panel there is dominated by
   * the per-lot history table, not the chart. */
  label?: string
}) {
  return (
    <button onClick={onToggle} style={{
      padding: '7px 13px',
      background: expanded ? 'var(--faint)' : 'transparent',
      border: '1px solid var(--border)', borderRadius: 8,
      color: 'var(--muted)', fontSize: 12, cursor: 'pointer',
    }}>{expanded ? '▲' : `▼ ${label}`}</button>
  )
}

export function ChartPanelBody({
  chart,
  indicators,
  height = 320,
}: {
  chart: UseQueryResult<ChartResponse>
  indicators: ChartIndicators
  height?: number
}) {
  if (chart.isLoading) return <div style={{ padding: 16 }}><Skeleton h={height} /></div>
  if (chart.error) return <div style={{ padding: 16 }}><ErrorBanner message="Chart data unavailable" /></div>
  if (!chart.data) return null
  return (
    <StockChart
      data={chart.data} height={height}
      showMACD={indicators.macd} showBB={indicators.bb} showGoldenCross={indicators.goldenCross}
    />
  )
}

/** Reusable Days-range pill control, shared by Signals and Positions. */
export function DaysControl({ days, setDays }: { days: number; setDays: (d: number) => void }) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', marginRight: 4 }}>Days</span>
      {[30, 60, 90, 180, 365].map(d => (
        <button key={d} onClick={() => setDays(d)} style={{
          padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
          border: `1px solid ${days === d ? 'var(--blue)' : 'var(--border)'}`,
          background: days === d ? 'var(--blue-bg)' : 'transparent',
          color: days === d ? 'var(--blue)' : 'var(--muted)', cursor: 'pointer',
        }}>{d}</button>
      ))}
    </div>
  )
}

/** Reusable indicator-overlay pill control (MACD/BB/GX), shared by Signals and Positions. */
export function OverlayControls({
  indicators,
  toggleIndicator,
}: {
  indicators: ChartIndicators
  toggleIndicator: (k: keyof ChartIndicators) => void
}) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', marginRight: 4 }}>Overlays</span>
      {([
        { k: 'macd', label: 'MACD' },
        { k: 'bb',   label: 'BB' },
        { k: 'goldenCross', label: 'GX' },
      ] as { k: keyof ChartIndicators; label: string }[]).map(({ k, label }) => (
        <button key={k} onClick={() => toggleIndicator(k)} style={{
          padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
          border: `1px solid ${indicators[k] ? 'var(--amber)' : 'var(--border)'}`,
          background: indicators[k] ? 'var(--amber-bg)' : 'transparent',
          color: indicators[k] ? 'var(--amber)' : 'var(--muted)', cursor: 'pointer',
        }}>{label}</button>
      ))}
    </div>
  )
}
