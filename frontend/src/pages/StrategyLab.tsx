import { useState, useMemo } from 'react'
import { useSignals, useCandidates, useCalibration, useRunBacktest, useNseSymbols } from '../api/hooks'
import { searchSymbols } from '../utils/symbolSearch'

const BACKTEST_BUNDLES = ['trend', 'breakout', 'reversal', 'vcp', 'composite'] as const

const STRATEGIES: { id: string; label: string; bucketPrefix: string; desc: string }[] = [
  { id: 'trend',    label: 'Trend Following',   bucketPrefix: 'trend',    desc: 'DMA alignment + momentum confirmation' },
  { id: 'breakout', label: 'Momentum Breakout', bucketPrefix: 'breakout', desc: '52w high breakout + volume surge' },
  { id: 'mean',     label: 'Mean Reversion',    bucketPrefix: 'mean',     desc: 'Bollinger Band squeeze + RSI extremes' },
  { id: 'accum',    label: 'Accumulation',      bucketPrefix: 'accum',    desc: 'Multi-tranche DCA on fundamental quality' },
]

const REGIMES = ['BULL', 'BEAR', 'SIDEWAYS'] as const
const SPRT_LABEL: Record<string, string> = {
  accept_H1: 'Edge confirmed',
  accept_H0: 'No edge',
  continue:  'Still monitoring',
}
const CONF_COLOR: Record<string, string> = {
  high:   'var(--green)',
  medium: 'var(--amber)',
  low:    'var(--red)',
}

export default function StrategyLab() {
  const [strategy, setStrategy] = useState('trend')
  const [regime,   setRegime]   = useState<string>('BULL')
  const [symbol,   setSymbol]   = useState('')
  const [query,    setQuery]    = useState('')
  const [mode,     setMode]     = useState<'universe' | 'single'>('universe')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [btBundle, setBtBundle] = useState<string>('trend')
  const [btLookback, setBtLookback] = useState<number>(365)
  const [btCosts, setBtCosts] = useState<boolean>(true)
  const [btFills, setBtFills] = useState<boolean>(true)

  const signals    = useSignals()
  const candidates = useCandidates()
  const calibration = useCalibration()
  const backtest    = useRunBacktest()
  const nseSymbols  = useNseSymbols()

  // Build searchable symbol list — full NSE universe, not just tracked signals/candidates
  const symbolList = useMemo(() => {
    const set = new Set<string>()
    nseSymbols.data?.forEach(s => { if (!s.includes('NSETEST')) set.add(s) })
    signals.data?.forEach(s => set.add(s.symbol))
    candidates.data?.forEach(c => set.add(c.symbol))
    return [...set].sort()
  }, [nseSymbols.data, signals.data, candidates.data])

  const filtered = useMemo(() =>
    query.length < 1 ? symbolList : searchSymbols(symbolList, query, 50),
    [symbolList, query]
  )

  // Filter calibration rows by selected strategy + regime
  const stratDef = STRATEGIES.find(s => s.id === strategy)!
  const relevantRows = useMemo(() => {
    if (!calibration.data) return []
    return calibration.data.filter(r =>
      r.bucket.startsWith(stratDef.bucketPrefix) &&
      r.regime === regime
    )
  }, [calibration.data, stratDef, regime])

  // Aggregate stats
  const stats = useMemo(() => {
    if (!relevantRows.length) return null
    const n       = relevantRows.reduce((s, r) => s + r.n_closed, 0)
    const avgWin  = relevantRows.reduce((s, r) => s + r.win_rate * r.n_closed, 0) / n
    const avgExp  = relevantRows.reduce((s, r) => s + r.expectancy_R * r.n_closed, 0) / n
    const highConf = relevantRows.filter(r => r.confidence_band === 'high').length
    const accepted = relevantRows.filter(r => r.sprt_state === 'accept_H1').length
    return { n, avgWin, avgExp, highConf, accepted, total: relevantRows.length }
  }, [relevantRows])

  const isLoading = calibration.isLoading || signals.isLoading || candidates.isLoading

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 760 }}>

      {/* Strategy selector */}
      <section>
        <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.06em' }}>STRATEGY</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
          {STRATEGIES.map(s => (
            <button key={s.id} onClick={() => setStrategy(s.id)} style={{
              background: strategy === s.id ? 'var(--blue-bg)' : 'var(--surface)',
              border: `1px solid ${strategy === s.id ? 'var(--blue)' : 'var(--border)'}`,
              color: strategy === s.id ? 'var(--blue)' : 'var(--text)',
              borderRadius: 10, padding: 14, textAlign: 'left',
              display: 'flex', flexDirection: 'column', gap: 4, cursor: 'pointer',
            }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{s.label}</span>
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>{s.desc}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Regime + scope */}
      <div style={{ display: 'flex', gap: 16 }}>
        <section style={{ flex: 1 }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.06em' }}>REGIME FILTER</p>
          <div style={{ display: 'flex', gap: 6 }}>
            {REGIMES.map(r => (
              <button key={r} onClick={() => setRegime(r)} style={{
                padding: '6px 16px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
                background: regime === r ? 'var(--faint)' : 'var(--surface)',
                border: `1px solid ${regime === r ? 'var(--blue)' : 'var(--border)'}`,
                color: regime === r ? 'var(--text)' : 'var(--muted)',
                fontWeight: regime === r ? 600 : 400,
              }}>{r}</button>
            ))}
          </div>
        </section>
        <section>
          <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.06em' }}>SCOPE</p>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['universe', 'single'] as const).map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                padding: '6px 16px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
                background: mode === m ? 'var(--faint)' : 'var(--surface)',
                border: `1px solid ${mode === m ? 'var(--blue)' : 'var(--border)'}`,
                color: mode === m ? 'var(--text)' : 'var(--muted)',
                fontWeight: mode === m ? 600 : 400,
              }}>{m === 'universe' ? 'Full Universe' : 'Single Stock'}</button>
            ))}
          </div>
        </section>
      </div>

      {/* Symbol picker */}
      {mode === 'single' && (
        <section style={{ position: 'relative' }}>
          <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.06em' }}>SYMBOL</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <input
                value={query}
                onChange={e => { setQuery(e.target.value); setDropdownOpen(true); setSymbol('') }}
                onFocus={() => setDropdownOpen(true)}
                onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                placeholder="Type to search symbols…"
                style={{
                  width: '100%', padding: '8px 12px',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 8, color: 'var(--text)', fontSize: 13, outline: 'none', boxSizing: 'border-box',
                }}
              />
              {dropdownOpen && filtered.length > 0 && (
                <div style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 8, marginTop: 4, maxHeight: 200, overflowY: 'auto',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                }}>
                  {filtered.slice(0, 50).map(s => (
                    <div
                      key={s}
                      onMouseDown={() => { setSymbol(s); setQuery(s); setDropdownOpen(false) }}
                      style={{
                        padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                        color: symbol === s ? 'var(--green)' : 'var(--text)',
                        background: symbol === s ? 'rgba(0,200,150,0.07)' : 'transparent',
                      }}
                    >{s}</div>
                  ))}
                </div>
              )}
            </div>
            {symbol && (
              <div style={{
                padding: '8px 14px', background: 'rgba(0,200,150,0.1)',
                border: '1px solid var(--green)', borderRadius: 8,
                color: 'var(--green)', fontSize: 13, fontWeight: 700,
                display: 'flex', alignItems: 'center',
              }}>{symbol}</div>
            )}
          </div>
        </section>
      )}

      {/* ── Performance Panel ───────────────────────────────────────────── */}
      <section>
        <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 12, letterSpacing: '0.06em' }}>
          HISTORICAL PERFORMANCE · {stratDef.label} · {regime}
        </p>

        {isLoading ? (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, textAlign: 'center', color: 'var(--dim)', fontSize: 13 }}>
            Loading calibration data…
          </div>
        ) : !stats ? (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 32, textAlign: 'center', color: 'var(--dim)', fontSize: 13 }}>
            No closed trades for <strong>{stratDef.label}</strong> in <strong>{regime}</strong> regime yet.
            Run the Sunday pipeline to accumulate calibration data.
          </div>
        ) : (
          <>
            {/* Aggregate KPIs */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 }}>
              {[
                { label: 'Closed Trades', value: stats.n.toString(), color: 'var(--text)' },
                { label: 'Win Rate', value: `${(stats.avgWin * 100).toFixed(1)}%`, color: stats.avgWin >= 0.55 ? 'var(--green)' : 'var(--amber)' },
                { label: 'Avg Expectancy', value: `${stats.avgExp.toFixed(2)}R`, color: stats.avgExp > 0 ? 'var(--green)' : 'var(--red)' },
                { label: 'Buckets w/ Edge', value: `${stats.accepted}/${stats.total}`, color: 'var(--blue)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 10, padding: '14px 16px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 6 }}>{label}</div>
                  <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
                </div>
              ))}
            </div>

            {/* Bucket breakdown */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
              <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ color: 'var(--dim)', fontSize: 10, borderBottom: '1px solid var(--border)' }}>
                    {['Score Bucket', 'Trades', 'Win Rate', 'Expectancy', 'CI Range', 'Status', 'Confidence'].map(h => (
                      <th key={h} style={{ padding: '9px 14px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {relevantRows.map(r => (
                    <tr key={r.bucket} style={{ borderBottom: '1px solid var(--faint)' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 600, color: 'var(--text)' }}>
                        {r.bucket.replace(stratDef.bucketPrefix + '_score_', '').replace('_', '–')}
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--muted)' }}>{r.n_closed}</td>
                      <td style={{ padding: '10px 14px', color: r.win_rate >= 0.55 ? 'var(--green)' : 'var(--amber)', fontWeight: 600 }}>
                        {(r.win_rate * 100).toFixed(0)}%
                      </td>
                      <td style={{ padding: '10px 14px', fontWeight: 700, color: r.expectancy_R > 0 ? 'var(--green)' : 'var(--red)' }}>
                        {r.expectancy_R > 0 ? '+' : ''}{r.expectancy_R.toFixed(2)}R
                      </td>
                      <td style={{ padding: '10px 14px', color: 'var(--dim)', fontSize: 11 }}>
                        [{r.ci_low_R.toFixed(2)}, {r.ci_high_R.toFixed(2)}]
                      </td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{
                          fontSize: 10, padding: '2px 7px', borderRadius: 4,
                          background: r.sprt_state === 'accept_H1' ? 'rgba(0,200,150,0.1)' : 'var(--faint)',
                          color: r.sprt_state === 'accept_H1' ? 'var(--green)' : 'var(--muted)',
                          fontWeight: 600,
                        }}>
                          {SPRT_LABEL[r.sprt_state] ?? r.sprt_state}
                        </span>
                      </td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{ fontSize: 11, color: CONF_COLOR[r.confidence_band] ?? 'var(--muted)', fontWeight: 600, textTransform: 'capitalize' }}>
                          {r.confidence_band}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p style={{ fontSize: 11, color: 'var(--dim)', marginTop: 8 }}>
              Based on {stats.n} closed trades from live pipeline runs. Expectancy is in R-multiples (1R = initial risk per trade).
              SPRT continuously monitors for regime shifts in win rate.
            </p>
          </>
        )}
      </section>

      {/* ── Run Backtest ───────────────────────────────────────────────── */}
      <section>
        <p style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.06em' }}>
          RUN BACKTEST
        </p>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 12, padding: 16,
        }}>
          <p style={{ fontSize: 11, color: 'var(--dim)', marginTop: 0, marginBottom: 14 }}>
            Single-symbol walk over the chosen window. Synthetic SIDEWAYS regime, in-sample —
            display only, not evidence for live sizing.
          </p>

          {/* Bundle picker */}
          <div style={{ marginBottom: 12 }}>
            <p style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 6, letterSpacing: '0.06em' }}>BUNDLE</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {BACKTEST_BUNDLES.map(b => (
                <button key={b} onClick={() => setBtBundle(b)} style={{
                  padding: '6px 14px', borderRadius: 8, fontSize: 12, cursor: 'pointer',
                  background: btBundle === b ? 'var(--blue-bg)' : 'var(--bg)',
                  border: `1px solid ${btBundle === b ? 'var(--blue)' : 'var(--border)'}`,
                  color: btBundle === b ? 'var(--blue)' : 'var(--muted)',
                  fontWeight: btBundle === b ? 600 : 400, textTransform: 'capitalize',
                }}>{b}</button>
              ))}
            </div>
          </div>

          {/* Symbol echo + lookback + toggles */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <p style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 6, letterSpacing: '0.06em' }}>SYMBOL</p>
              <div style={{
                padding: '8px 12px', background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: symbol ? 'var(--text)' : 'var(--dim)', fontSize: 13,
                fontWeight: symbol ? 700 : 400,
              }}>
                {symbol || 'Pick a symbol above (Scope → Single Stock)'}
              </div>
            </div>
            <div>
              <p style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 6, letterSpacing: '0.06em' }}>
                LOOKBACK · {btLookback}d
              </p>
              <input
                type="range"
                min={90}
                max={730}
                step={30}
                value={btLookback}
                onChange={e => setBtLookback(parseInt(e.target.value, 10))}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 14, fontSize: 12, color: 'var(--muted)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={btCosts} onChange={e => setBtCosts(e.target.checked)} />
              Cost model
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={btFills} onChange={e => setBtFills(e.target.checked)} />
              Fill policy
            </label>
          </div>

          <button
            onClick={() => {
              if (!symbol) return
              backtest.mutate({
                bundle: btBundle,
                symbol,
                lookback_days: btLookback,
                use_cost_model: btCosts,
                use_fill_policy: btFills,
              })
            }}
            disabled={!symbol || backtest.isPending}
            style={{
              padding: '10px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600,
              background: !symbol || backtest.isPending ? 'var(--faint)' : 'var(--blue)',
              color: !symbol || backtest.isPending ? 'var(--dim)' : 'white',
              border: 'none',
              cursor: !symbol || backtest.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {backtest.isPending ? 'Running…' : '▶ Run Backtest'}
          </button>

          {!symbol && (
            <p style={{ fontSize: 11, color: 'var(--amber)', marginTop: 10 }}>
              Select a symbol above (set Scope to “Single Stock”) before running.
            </p>
          )}

          {backtest.isError && (
            <p style={{ fontSize: 12, color: 'var(--red)', marginTop: 10 }}>
              {(backtest.error as { response?: { data?: { detail?: string } } })?.response?.data
                ?.detail ?? 'Backtest failed.'}
            </p>
          )}

          {backtest.data && (
            <div style={{ marginTop: 16 }}>
              <p style={{ fontSize: 11, color: 'var(--dim)', marginBottom: 10 }}>
                {backtest.data.bundle} · {backtest.data.symbol} · {backtest.data.start} → {backtest.data.end}
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 12 }}>
                {[
                  { label: 'Trades', value: backtest.data.n_trades.toString(), color: 'var(--text)' },
                  {
                    label: 'Win Rate',
                    value: backtest.data.n_trades ? `${(backtest.data.win_rate * 100).toFixed(1)}%` : '—',
                    color: backtest.data.win_rate >= 0.5 ? 'var(--green)' : 'var(--amber)',
                  },
                  {
                    label: 'Expectancy',
                    value: backtest.data.n_trades ? `${backtest.data.expectancy_R >= 0 ? '+' : ''}${backtest.data.expectancy_R.toFixed(2)}R` : '—',
                    color: backtest.data.expectancy_R > 0 ? 'var(--green)' : 'var(--red)',
                  },
                  {
                    label: 'Sum R',
                    value: backtest.data.n_trades ? `${backtest.data.sum_R >= 0 ? '+' : ''}${backtest.data.sum_R.toFixed(2)}R` : '—',
                    color: backtest.data.sum_R > 0 ? 'var(--green)' : 'var(--red)',
                  },
                ].map(({ label, value, color }) => (
                  <div key={label} style={{
                    background: 'var(--bg)', border: '1px solid var(--border)',
                    borderRadius: 10, padding: '12px 14px', textAlign: 'center',
                  }}>
                    <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 4 }}>{label}</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
                  </div>
                ))}
              </div>

              {backtest.data.n_trades === 0 ? (
                <p style={{ fontSize: 12, color: 'var(--dim)' }}>
                  No trades produced — bundle never fit a signal in the window, or every signal was filtered by the fill policy.
                </p>
              ) : (
                <>
                  <p style={{ fontSize: 11, color: 'var(--dim)', marginBottom: 8 }}>
                    Avg hold {backtest.data.avg_hold_days.toFixed(1)}d · lookahead violations {backtest.data.fills_before_signal} ·
                    costs={backtest.data.cost_model_on ? 'on' : 'off'} · fills={backtest.data.fill_policy_on ? 'on' : 'off'}
                  </p>
                  <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden', maxHeight: 280, overflowY: 'auto' }}>
                    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                      <thead style={{ position: 'sticky', top: 0, background: 'var(--bg)' }}>
                        <tr style={{ color: 'var(--dim)', fontSize: 10, borderBottom: '1px solid var(--border)' }}>
                          {['Entry', 'Exit', 'Hold', 'R'].map(h => (
                            <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {backtest.data.trades.map((t, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid var(--faint)' }}>
                            <td style={{ padding: '8px 12px', color: 'var(--text)' }}>{t.entry_date.slice(0, 10)}</td>
                            <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{t.exit_date.slice(0, 10)}</td>
                            <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{t.hold_days}d</td>
                            <td style={{ padding: '8px 12px', fontWeight: 700, color: t.realized_R > 0 ? 'var(--green)' : 'var(--red)' }}>
                              {t.realized_R > 0 ? '+' : ''}{t.realized_R.toFixed(2)}R
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
