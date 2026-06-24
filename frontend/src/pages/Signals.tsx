import { useState, useMemo, useEffect } from 'react'
import { useSignals, useChart, useEnterSignal, useSwingPositions, useLTP } from '../api/hooks'
import { PillarBar } from '../components/ui/PillarBar'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { StockChart } from '../components/chart/StockChart'
import type { SwingSignal } from '../types/api'

const PILLAR_DEFS: { key: keyof SwingSignal['pillar_breakdown']; label: string }[] = [
  { key: 'technical',    label: 'Technical' },
  { key: 'expectancy',   label: 'Expectancy' },
  { key: 'flow',         label: 'Flow' },
  { key: 'sentiment',    label: 'Sentiment' },
  { key: 'regime_fit',   label: 'Regime fit' },
  { key: 'fundamentals', label: 'Fundamentals' },
]

const LABEL_STYLE: Record<string, { bg: string; color: string }> = {
  BUY:   { bg: 'rgba(0,200,150,0.1)',  color: 'var(--green)' },
  SELL:  { bg: 'rgba(242,54,69,0.1)',  color: 'var(--red)' },
  EXIT:  { bg: 'rgba(245,158,11,0.1)', color: 'var(--amber)' },
  WATCH: { bg: 'var(--faint)',          color: 'var(--muted)' },
}

const ACCENT: Record<string, string> = {
  BUY:   'var(--green)',
  SELL:  'var(--red)',
  EXIT:  'var(--amber)',
  WATCH: 'var(--border)',
}

type Indicators = { macd: boolean; bb: boolean; goldenCross: boolean }
type SortKey = 'score' | 'label'

// ── Trade entry modal ─────────────────────────────────────────────────────────

function TradeModal({
  signal,
  defaultSide,
  onClose,
}: {
  signal: SwingSignal
  defaultSide: 'BUY' | 'SELL'
  onClose: () => void
}) {
  const priceQuery = useLTP(signal.symbol)
  const cmp = priceQuery.data ?? null

  const [side, setSide]   = useState<'BUY' | 'SELL'>(defaultSide)
  const [price, setPrice] = useState('')
  const [qty, setQty]     = useState('')

  const enterSignal = useEnterSignal()

  const suggestedEntry = parseFloat(signal.entry)
  const sl  = parseFloat(signal.stop_loss)
  const t1  = parseFloat(signal.target_1)
  const t2  = parseFloat(signal.target_2)

  // Pre-fill with signal's recommended entry
  useEffect(() => {
    if (price === '') {
      setPrice(suggestedEntry > 0 ? suggestedEntry.toFixed(2) : (cmp?.toFixed(2) ?? ''))
    }
  }, [cmp])

  const priceVal = parseFloat(price)
  const qtyVal   = parseInt(qty, 10)
  const isValid  = !isNaN(priceVal) && priceVal > 0 && !isNaN(qtyVal) && qtyVal > 0

  const handleSubmit = () => {
    if (!isValid) return
    enterSignal.mutate(
      { signalId: signal.id, side, qty: qtyVal, price: priceVal },
      { onSuccess: () => onClose() },
    )
  }

  const handleBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

  const rr = suggestedEntry > 0 && sl > 0 && t1 > 0
    ? Math.abs((t1 - suggestedEntry) / (suggestedEntry - sl)).toFixed(1)
    : null

  const labelStyle = LABEL_STYLE[signal.label] ?? LABEL_STYLE.WATCH
  const isLong = side === 'BUY'

  return (
    <div
      onClick={handleBackdrop}
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        backdropFilter: 'blur(2px)',
      }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: 28, width: 440, maxWidth: '92vw',
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 800, fontSize: 18 }}>{signal.symbol}</span>
              <span style={{
                fontSize: 11, padding: '2px 8px', borderRadius: 6,
                background: labelStyle.bg, color: labelStyle.color, fontWeight: 700,
              }}>{signal.label}</span>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{signal.score}/100</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--dim)' }}>
              {signal.calibration_band} · {signal.regime_at_signal}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--muted)',
            fontSize: 18, cursor: 'pointer', padding: '0 4px', lineHeight: 1,
          }}>✕</button>
        </div>

        {/* Signal levels */}
        {suggestedEntry > 0 && (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8,
            background: 'var(--faint)', borderRadius: 10, padding: '12px 14px',
          }}>
            {[
              { label: 'Entry', value: suggestedEntry, color: 'var(--text)' },
              { label: 'Stop Loss', value: sl, color: 'var(--red)' },
              { label: 'Target 1', value: t1, color: 'var(--green)' },
              { label: 'Target 2', value: t2 > 0 ? t2 : null, color: 'var(--blue)' },
            ].map(({ label, value, color }) => value ? (
              <div key={label} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color }}>
                  ₹{value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                </div>
              </div>
            ) : null)}
            {rr && (
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>R:R</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--blue)' }}>{rr}x</div>
              </div>
            )}
          </div>
        )}

        {/* CMP */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--faint)', borderRadius: 10, padding: '10px 14px',
        }}>
          <div>
            <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>CURRENT MARKET PRICE</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>
              {priceQuery.isLoading ? 'Fetching…' : cmp != null
                ? `₹${cmp.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : '—'}
            </div>
          </div>
          {cmp != null && (
            <button onClick={() => setPrice(cmp.toFixed(2))} style={{
              fontSize: 11, padding: '4px 10px',
              background: 'rgba(0,200,150,0.1)', border: '1px solid var(--green)',
              borderRadius: 6, color: 'var(--green)', cursor: 'pointer',
            }}>Use CMP</button>
          )}
          {suggestedEntry > 0 && (
            <button onClick={() => setPrice(suggestedEntry.toFixed(2))} style={{
              fontSize: 11, padding: '4px 10px',
              background: 'var(--faint)', border: '1px solid var(--border)',
              borderRadius: 6, color: 'var(--muted)', cursor: 'pointer',
            }}>Use Signal Entry</button>
          )}
        </div>

        {/* Side selector */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.05em' }}>
            DIRECTION
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {(['BUY', 'SELL'] as const).map(s => (
              <button
                key={s}
                onClick={() => setSide(s)}
                style={{
                  flex: 1, padding: '9px 0', borderRadius: 9, fontSize: 13, fontWeight: 700, cursor: 'pointer',
                  background: side === s
                    ? (s === 'BUY' ? 'rgba(0,200,150,0.15)' : 'rgba(242,54,69,0.15)')
                    : 'var(--faint)',
                  border: `1px solid ${side === s ? (s === 'BUY' ? 'var(--green)' : 'var(--red)') : 'var(--border)'}`,
                  color: side === s ? (s === 'BUY' ? 'var(--green)' : 'var(--red)') : 'var(--muted)',
                }}
              >
                {s === 'BUY' ? '↑ Long (Buy)' : '↓ Short (Sell)'}
              </button>
            ))}
          </div>
        </div>

        {/* Price + Qty */}
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: 5 }}>
              ENTRY PRICE (₹)
            </label>
            <input
              value={price}
              onChange={e => setPrice(e.target.value)}
              placeholder={suggestedEntry > 0 ? suggestedEntry.toFixed(2) : 'e.g. 1234.50'}
              style={{
                width: '100%', padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: 5 }}>
              SHARES
            </label>
            <input
              value={qty}
              onChange={e => setQty(e.target.value)}
              type="number"
              min="1"
              placeholder="e.g. 10"
              style={{
                width: '100%', padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Total cost preview */}
        {isValid && (
          <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'right' }}>
            Total: <strong style={{ color: 'var(--text)' }}>
              ₹{(priceVal * qtyVal).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </strong>
          </div>
        )}

        {/* Error */}
        {enterSignal.isError && (
          <div style={{ fontSize: 12, color: 'var(--red)', background: 'rgba(242,54,69,0.08)', padding: '8px 12px', borderRadius: 8 }}>
            {String(enterSignal.error)}
          </div>
        )}

        {/* Footer */}
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose} style={{
            flex: 1, padding: '10px 0',
            background: 'transparent', border: '1px solid var(--border)',
            borderRadius: 10, color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
          }}>Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || enterSignal.isPending}
            style={{
              flex: 2, padding: '10px 0',
              background: isValid ? (isLong ? 'var(--green)' : 'var(--red)') : 'var(--faint)',
              border: 'none', borderRadius: 10,
              color: isValid ? '#000' : 'var(--dim)',
              fontSize: 13, fontWeight: 700,
              cursor: isValid && !enterSignal.isPending ? 'pointer' : 'default',
              opacity: enterSignal.isPending ? 0.6 : 1,
            }}
          >
            {enterSignal.isPending ? 'Placing…' : `${isLong ? 'Buy' : 'Sell'} ${qtyVal || '—'} shares @ ₹${price || '—'}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Controls pill ─────────────────────────────────────────────────────────────

function Pill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
      border: `1px solid ${active ? 'var(--green)' : 'var(--border)'}`,
      background: active ? 'rgba(0,200,150,0.1)' : 'transparent',
      color: active ? 'var(--green)' : 'var(--muted)',
      cursor: 'pointer',
    }}>{label}</button>
  )
}

// ── Signal card ───────────────────────────────────────────────────────────────

function SignalCard({
  signal,
  chartDays,
  indicators,
  ownedSymbols,
}: {
  signal: SwingSignal
  chartDays: number
  indicators: Indicators
  ownedSymbols: Set<string>
}) {
  const [expanded, setExpanded] = useState(false)
  const [tradeModal, setTradeModal] = useState<'BUY' | 'SELL' | null>(null)
  const chart = useChart(signal.symbol, signal.id, chartDays, expanded)

  const labelStyle = LABEL_STYLE[signal.label] ?? LABEL_STYLE.WATCH
  const accentColor = ACCENT[signal.label] ?? 'var(--border)'
  const isBuy   = signal.label === 'BUY'
  const isSell  = signal.label === 'SELL'
  const isWatch = !isBuy && !isSell
  const userOwns = ownedSymbols.has(signal.symbol)

  const entry = parseFloat(signal.entry)
  const sl    = parseFloat(signal.stop_loss)
  const t1    = parseFloat(signal.target_1)
  const hasLevels = entry > 0 && sl > 0
  const rr    = hasLevels && t1 > 0 ? ((t1 - entry) / Math.abs(entry - sl)).toFixed(1) : null

  return (
    <>
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderLeft: `3px solid ${accentColor}`, borderRadius: 12, overflow: 'hidden',
      }}>
        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <span style={{ fontWeight: 700, fontSize: 14 }}>{signal.symbol}</span>
              <span style={{
                fontSize: 11, padding: '2px 8px', borderRadius: 6,
                background: labelStyle.bg, color: labelStyle.color,
                fontWeight: 700, letterSpacing: '0.04em',
              }}>{signal.label}</span>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{signal.score}/100</span>
              <span style={{ fontSize: 11, color: 'var(--dim)' }}>
                {signal.calibration_band} · {signal.regime_at_signal}
              </span>
            </div>
            {hasLevels && (
              <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--muted)' }}>
                <span>Entry <strong style={{ color: 'var(--text)' }}>₹{entry.toLocaleString('en-IN')}</strong></span>
                <span style={{ color: 'var(--red)' }}>SL ₹{sl.toLocaleString('en-IN')}</span>
                <span style={{ color: 'var(--green)' }}>T1 ₹{t1.toLocaleString('en-IN')}</span>
                {parseFloat(signal.target_2) > 0 && (
                  <span style={{ color: 'var(--blue)' }}>T2 ₹{parseFloat(signal.target_2).toLocaleString('en-IN')}</span>
                )}
                {rr && <span style={{ color: 'var(--blue)' }}>R:R {rr}x</span>}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: 6 }}>
            {/* BUY signal → Buy button always, Sell only if user owns the stock */}
            {isBuy && (
              <button onClick={() => setTradeModal('BUY')} style={{
                padding: '7px 13px',
                background: 'rgba(0,200,150,0.12)', border: '1px solid var(--green)',
                borderRadius: 8, color: 'var(--green)', fontSize: 12, fontWeight: 700, cursor: 'pointer',
              }}>↑ Buy</button>
            )}
            {/* SELL signal → pipeline says sell; only show if user actually owns it */}
            {isSell && userOwns && (
              <button onClick={() => setTradeModal('SELL')} style={{
                padding: '7px 13px',
                background: 'rgba(242,54,69,0.12)', border: '1px solid var(--red)',
                borderRadius: 8, color: 'var(--red)', fontSize: 12, fontWeight: 700, cursor: 'pointer',
              }}>↓ Sell</button>
            )}
            {isSell && !userOwns && (
              <span style={{ fontSize: 11, color: 'var(--dim)', padding: '7px 2px' }}>Not owned</span>
            )}
            {/* WATCH/EXIT → Buy always, Sell only if owned */}
            {isWatch && (
              <>
                <button onClick={() => setTradeModal('BUY')} style={{
                  padding: '5px 10px',
                  background: 'rgba(0,200,150,0.08)', border: '1px solid rgba(0,200,150,0.35)',
                  borderRadius: 7, color: 'var(--green)', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                }}>↑ Buy</button>
                {userOwns && (
                  <button onClick={() => setTradeModal('SELL')} style={{
                    padding: '5px 10px',
                    background: 'rgba(242,54,69,0.08)', border: '1px solid rgba(242,54,69,0.35)',
                    borderRadius: 7, color: 'var(--red)', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                  }}>↓ Sell</button>
                )}
              </>
            )}
            <button onClick={() => setExpanded(e => !e)} style={{
              padding: '7px 13px',
              background: expanded ? 'var(--faint)' : 'transparent',
              border: '1px solid var(--border)', borderRadius: 8,
              color: 'var(--muted)', fontSize: 12, cursor: 'pointer',
            }}>{expanded ? '▲' : '▼ Chart'}</button>
          </div>
        </div>

        {/* Pillar bars */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '8px 24px', padding: '0 16px 14px',
        }}>
          {PILLAR_DEFS.map(({ key, label }) => (
            <PillarBar key={key} label={label} value={signal.pillar_breakdown?.[key] ?? 0} />
          ))}
        </div>

        {/* Chart */}
        {expanded && (
          <div style={{ borderTop: '1px solid var(--border)' }}>
            {chart.isLoading ? (
              <div style={{ padding: 16 }}><Skeleton h={320} /></div>
            ) : chart.error ? (
              <div style={{ padding: 16 }}><ErrorBanner message="Chart data unavailable" /></div>
            ) : chart.data ? (
              <StockChart
                data={chart.data} height={320}
                showMACD={indicators.macd} showBB={indicators.bb} showGoldenCross={indicators.goldenCross}
              />
            ) : null}
            {signal.counterfactual && (
              <div style={{ padding: '10px 16px', borderTop: '1px solid var(--faint)', fontSize: 12, color: 'var(--dim)' }}>
                {signal.counterfactual}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Trade modal */}
      {tradeModal && (
        <TradeModal
          signal={signal}
          defaultSide={tradeModal}
          onClose={() => setTradeModal(null)}
        />
      )}
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Signals() {
  const { data, isLoading, error } = useSignals()
  const { data: swingPositions } = useSwingPositions()

  const ownedSymbols = useMemo(() => {
    const s = new Set<string>()
    for (const t of swingPositions ?? []) {
      if (t.state === 'OPEN') s.add(t.symbol)
    }
    return s
  }, [swingPositions])

  const [days, setDays]   = useState(90)
  const [sort, setSort]   = useState<SortKey>('score')
  const [labelFilter, setLabelFilter] = useState<string | null>(null)
  const [indicators, setIndicators] = useState<Indicators>({ macd: false, bb: false, goldenCross: false })

  const toggleInd = (k: keyof Indicators) =>
    setIndicators(prev => ({ ...prev, [k]: !prev[k] }))

  const sorted = useMemo(() => {
    if (!data) return []
    let out = [...data]
    if (labelFilter) out = out.filter(s => s.label === labelFilter)
    if (sort === 'score') out.sort((a, b) => b.score - a.score)
    else {
      const order: Record<string, number> = { BUY: 0, SELL: 1, EXIT: 2, WATCH: 3 }
      out.sort((a, b) => (order[a.label] ?? 9) - (order[b.label] ?? 9) || b.score - a.score)
    }
    return out
  }, [data, sort, labelFilter])

  const labels = useMemo(() => {
    if (!data) return []
    return [...new Set(data.map(s => s.label))].sort()
  }, [data])

  if (error) return <ErrorBanner message={String(error)} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 820 }}>
      {/* Controls */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center',
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 10, padding: '10px 14px',
      }}>
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
        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--muted)', marginRight: 4 }}>Sort</span>
          {(['score', 'label'] as SortKey[]).map(s => (
            <button key={s} onClick={() => setSort(s)} style={{
              padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
              border: `1px solid ${sort === s ? 'var(--blue)' : 'var(--border)'}`,
              background: sort === s ? 'var(--blue-bg)' : 'transparent',
              color: sort === s ? 'var(--blue)' : 'var(--muted)', cursor: 'pointer',
            }}>{s === 'score' ? 'Score ↓' : 'By Label'}</button>
          ))}
        </div>
        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
        <div style={{ display: 'flex', gap: 4 }}>
          <Pill label="All" active={!labelFilter} onClick={() => setLabelFilter(null)} />
          {labels.map(l => (
            <Pill key={l} label={l} active={labelFilter === l} onClick={() => setLabelFilter(l === labelFilter ? null : l)} />
          ))}
        </div>
        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--muted)', marginRight: 4 }}>Overlays</span>
          {([
            { k: 'macd', label: 'MACD' },
            { k: 'bb',   label: 'BB' },
            { k: 'goldenCross', label: 'GX' },
          ] as { k: keyof Indicators; label: string }[]).map(({ k, label }) => (
            <button key={k} onClick={() => toggleInd(k)} style={{
              padding: '3px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
              border: `1px solid ${indicators[k] ? 'var(--amber)' : 'var(--border)'}`,
              background: indicators[k] ? 'var(--amber-bg)' : 'transparent',
              color: indicators[k] ? 'var(--amber)' : 'var(--muted)', cursor: 'pointer',
            }}>{label}</button>
          ))}
        </div>
      </div>

      <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
        {isLoading ? 'Loading…' : `${sorted.length} signal${sorted.length !== 1 ? 's' : ''} · latest run`}
      </p>

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[...Array(4)].map((_, i) => <Skeleton key={i} h={120} />)}
        </div>
      ) : !sorted.length ? (
        <p style={{ fontSize: 13, color: 'var(--dim)', padding: '32px 0', textAlign: 'center' }}>
          No signals match the current filter.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {sorted.map(s => (
            <SignalCard key={s.id} signal={s} chartDays={days} indicators={indicators} ownedSymbols={ownedSymbols} />
          ))}
        </div>
      )}
    </div>
  )
}
