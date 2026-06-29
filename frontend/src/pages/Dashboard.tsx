import { useRegime, usePortfolioSnapshot, useRunLog } from '../api/hooks'
import { StatCard } from '../components/ui/StatCard'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'

const REGIME_COLOR: Record<string, string> = {
  BULL: 'var(--green)', BEAR: 'var(--red)', SIDEWAYS: 'var(--amber)',
}

function fmt(n: number) { return `₹${n.toLocaleString('en-IN')}` }

export default function Dashboard() {
  const regime = useRegime()
  const portfolio = usePortfolioSnapshot()
  const runLog = useRunLog(5)

  if (regime.error) return <ErrorBanner message={String(regime.error)} />

  const r = regime.data
  const p = portfolio.data
  const color = r ? (REGIME_COLOR[r.label] ?? 'var(--dim)') : 'var(--dim)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 900 }}>

      {/* Regime banner */}
      {r ? (
        <div style={{
          background: 'var(--surface)',
          border: `1px solid ${color}`,
          borderRadius: 12,
          padding: '14px 20px',
          display: 'grid',
          gridTemplateColumns: 'auto 1fr 1fr 1fr 1fr',
          gap: 20,
          alignItems: 'center',
        }}>
          <div>
            <span style={{
              color,
              fontWeight: 700,
              fontSize: 18,
              letterSpacing: '-0.02em',
            }}>{r.label}</span>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
              {new Date(r.as_of_date).toLocaleDateString('en-IN')}
            </div>
          </div>
          {[
            { label: 'India VIX', value: r.india_vix.toFixed(1) },
            { label: 'Above 50 DMA', value: `${r.pct_above_50dma?.toFixed(1) ?? '—'}%` },
            { label: 'Above 200 DMA', value: `${r.pct_above_200dma?.toFixed(1) ?? '—'}%` },
            { label: 'Adv/Dec', value: r.advance_decline?.toFixed(2) ?? '—' },
          ].map(({ label, value }) => (
            <div key={label}>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</div>
              <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2 }}>{value}</div>
            </div>
          ))}
        </div>
      ) : (
        <Skeleton h={64} />
      )}

      {/* Portfolio stat cards */}
      {p ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          <StatCard label="Invested" value={fmt(p.total_invested)} />
          <StatCard label="Current Value" value={fmt(p.total_current)}
            trend={p.total_current >= p.total_invested ? 'up' : 'down'} />
          <StatCard label="Unrealised P&L" value={fmt(p.total_pnl)}
            sub={`${p.total_pnl_pct >= 0 ? '+' : ''}${p.total_pnl_pct.toFixed(2)}%`}
            trend={p.total_pnl >= 0 ? 'up' : 'down'} />
          <StatCard label="Open Positions" value={String(p.positions.length)} trend="neutral" />
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[...Array(4)].map((_, i) => <Skeleton key={i} h={80} />)}
        </div>
      )}

      {/* Positions mini-table */}
      {p && p.positions.length > 0 && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600 }}>
            Open Positions
          </div>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--muted)' }}>
                {['Symbol', 'Qty', 'Avg', 'CMP', 'SL', 'P&L', 'P&L %'].map(h => (
                  <th key={h} style={{ padding: '8px 16px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {p.positions.map(pos => (
                <tr key={pos.symbol} style={{ borderTop: '1px solid var(--faint)' }}>
                  <td style={{ padding: '9px 16px', fontWeight: 600 }}>{pos.symbol}</td>
                  <td style={{ padding: '9px 16px', color: 'var(--muted)' }}>{pos.qty}</td>
                  <td style={{ padding: '9px 16px' }}>₹{pos.avg_cost.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '9px 16px' }}>₹{pos.current_price.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '9px 16px', color: 'var(--red)' }}>₹{pos.stop_loss.toLocaleString('en-IN')}</td>
                  <td style={{ padding: '9px 16px', color: pos.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {pos.pnl >= 0 ? '+' : ''}₹{pos.pnl.toLocaleString('en-IN')}
                  </td>
                  <td style={{ padding: '9px 16px', color: pos.pnl_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Run log */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: 13, fontWeight: 600 }}>
          Recent Pipeline Runs
        </div>
        {runLog.isLoading ? (
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[...Array(3)].map((_, i) => <Skeleton key={i} h={36} />)}
          </div>
        ) : (runLog.data ?? []).length === 0 ? (
          <p style={{ padding: '24px 16px', textAlign: 'center', fontSize: 13, color: 'var(--dim)' }}>
            No runs yet — use "Trigger Run" above to start the Sunday pipeline.
          </p>
        ) : (
          <div>
            {(runLog.data ?? []).map(row => (
              <div key={row.run_id} style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '11px 16px',
                borderBottom: '1px solid var(--faint)',
              }}>
                <div>
                  <span style={{ fontSize: 13 }}>{row.job_name}</span>
                  <span style={{ fontSize: 11, marginLeft: 10, color: 'var(--muted)' }}>
                    {new Date(row.started_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                  </span>
                </div>
                <span style={{
                  fontSize: 11,
                  fontFamily: 'monospace',
                  padding: '2px 8px',
                  borderRadius: 6,
                  background: row.status === 'ok' ? 'var(--green-bg)' : 'var(--red-bg)',
                  color: row.status === 'ok' ? 'var(--green)' : 'var(--red)',
                }}>
                  {row.status?.toUpperCase() ?? 'RUNNING'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
