import { useState, useMemo } from 'react'
import { useNseSymbols, useQuickScore } from '../api/hooks'
import { PillarBar } from './ui/PillarBar'
import {
  useChartPanel, ChartToggleButton, ChartPanelBody, DaysControl, OverlayControls,
  DEFAULT_CHART_INDICATORS, type ChartIndicators,
} from './chart/ChartPanel'
import { searchSymbols } from '../utils/symbolSearch'
import type { SwingSignal } from '../types/api'

const QS_LABEL_STYLE: Record<string, { bg: string; color: string }> = {
  BUY:       { bg: 'rgba(0,200,150,0.1)',  color: 'var(--green)' },
  BUY_WATCH: { bg: 'rgba(0,200,150,0.1)',  color: 'var(--green)' },
  WATCH:     { bg: 'var(--faint)',          color: 'var(--muted)' },
  HOLD:      { bg: 'var(--faint)',          color: 'var(--muted)' },
}

// Same watch-screen scoring path as the Sunday pipeline, run on demand for any symbol.
function QuickScoreCard({ symbol, days, indicators }: { symbol: string; days: number; indicators: ChartIndicators }) {
  const score = useQuickScore(symbol)
  const { expanded, setExpanded, chart } = useChartPanel(symbol, undefined, days)

  if (score.isLoading) {
    return (
      <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, textAlign: 'center', color: 'var(--dim)', fontSize: 12 }}>
        Scoring {symbol}…
      </div>
    )
  }

  if (score.isError) {
    const detail = (score.error as { response?: { status?: number; data?: { message?: string } } })?.response
    const message = detail?.data?.message
      ?? (detail?.status === 422 ? `No actionable setup for ${symbol} under current momentum criteria` : `Couldn't score ${symbol}`)
    return (
      <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: 16, textAlign: 'center', color: 'var(--dim)', fontSize: 12 }}>
        {message}
      </div>
    )
  }

  const s = score.data as SwingSignal
  const labelStyle = QS_LABEL_STYLE[s.label] ?? QS_LABEL_STYLE.WATCH
  const entry = parseFloat(s.entry)
  const sl    = parseFloat(s.stop_loss)
  const t1    = parseFloat(s.target_1)
  const t2    = parseFloat(s.target_2)

  return (
    <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ padding: '12px 14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, fontSize: 13 }}>{s.symbol}</span>
          <span style={{
            fontSize: 10, padding: '2px 7px', borderRadius: 6,
            background: labelStyle.bg, color: labelStyle.color,
            fontWeight: 700, letterSpacing: '0.04em',
          }}>{s.label}</span>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{s.score}/100</span>
        </div>
        <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 8 }}>
          {s.regime_at_signal} · quick score, not persisted
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
          <span>Entry <strong style={{ color: 'var(--text)' }}>₹{entry.toLocaleString('en-IN')}</strong></span>
          <span style={{ color: 'var(--red)' }}>SL ₹{sl.toLocaleString('en-IN')}</span>
          <span style={{ color: 'var(--green)' }}>T1 ₹{t1.toLocaleString('en-IN')}</span>
          <span style={{ color: 'var(--blue)' }}>T2 ₹{t2.toLocaleString('en-IN')}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
          <PillarBar label="Technical" value={s.pillar_breakdown.technical} />
          <PillarBar label="Expectancy" value={s.pillar_breakdown.expectancy} />
          <PillarBar label="Flow" value={s.pillar_breakdown.flow} />
          <PillarBar label="Sentiment" value={s.pillar_breakdown.sentiment} />
          <PillarBar label="Regime fit" value={s.pillar_breakdown.regime_fit} />
          <PillarBar label="Fundamentals" value={s.pillar_breakdown.fundamentals} />
        </div>
        <ChartToggleButton expanded={expanded} onToggle={() => setExpanded(e => !e)} />
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)' }}>
          <ChartPanelBody chart={chart} indicators={indicators} height={220} />
        </div>
      )}
    </div>
  )
}

export function QuickScoreWidget() {
  const [query, setQuery] = useState('')
  const [symbol, setSymbol] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [days, setDays] = useState(90)
  const [indicators, setIndicators] = useState<ChartIndicators>(DEFAULT_CHART_INDICATORS)
  const toggleInd = (k: keyof ChartIndicators) =>
    setIndicators(prev => ({ ...prev, [k]: !prev[k] }))

  const nseSymbols = useNseSymbols()
  const filtered = useMemo(() => searchSymbols(nseSymbols.data ?? [], query), [nseSymbols.data, query])

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 12, padding: 14,
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', margin: 0, letterSpacing: '0.06em' }}>
        QUICK SCORE · ANY STOCK
      </p>

      <div style={{ position: 'relative' }}>
        <input
          value={query}
          onChange={e => { setQuery(e.target.value); setDropdownOpen(true); setSymbol('') }}
          onFocus={() => setDropdownOpen(true)}
          onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
          placeholder="Search NSE symbol…"
          style={{
            width: '100%', padding: '8px 12px',
            background: 'var(--bg)', border: '1px solid var(--border)',
            borderRadius: 8, color: 'var(--text)', fontSize: 13, outline: 'none', boxSizing: 'border-box',
          }}
        />
        {dropdownOpen && filtered.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
            background: 'var(--bg)', border: '1px solid var(--border)',
            borderRadius: 8, marginTop: 4, maxHeight: 200, overflowY: 'auto',
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}>
            {filtered.map(s => (
              <div
                key={s}
                onMouseDown={() => { setSymbol(s); setQuery(s); setDropdownOpen(false) }}
                style={{
                  padding: '7px 12px', fontSize: 12, cursor: 'pointer',
                  color: symbol === s ? 'var(--green)' : 'var(--text)',
                  background: symbol === s ? 'rgba(0,200,150,0.07)' : 'transparent',
                }}
              >{s}</div>
            ))}
          </div>
        )}
      </div>

      {symbol && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            <DaysControl days={days} setDays={setDays} />
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            <OverlayControls indicators={indicators} toggleIndicator={toggleInd} />
          </div>
          <QuickScoreCard symbol={symbol} days={days} indicators={indicators} />
        </>
      )}
    </div>
  )
}
