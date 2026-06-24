import {
  useAccumulationPositions,
  usePauseAccumulationPosition,
  useResumeAccumulationPosition,
  useExitAccumulationPosition,
} from '../api/hooks'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { PauseIcon, PlayIcon, XIcon } from '../components/icons'

const STATE_STYLE: Record<string, { bg: string; color: string }> = {
  ACTIVE:  { bg: 'rgba(0,200,150,0.1)', color: 'var(--green)' },
  PAUSED:  { bg: 'rgba(245,158,11,0.1)', color: 'var(--amber)' },
  EXITED:  { bg: 'var(--faint)', color: 'var(--dim)' },
}

export default function AccumulationPositions() {
  const { data, isLoading, error } = useAccumulationPositions()
  const pause = usePauseAccumulationPosition()
  const resume = useResumeAccumulationPosition()
  const exit = useExitAccumulationPosition()

  if (error) return <ErrorBanner message={String(error)} />

  const positions = data ?? []
  const active = positions.filter(p => p.state !== 'EXITED').length

  const handleExit = (id: number, symbol: string, qty: number) => {
    const priceStr = prompt(`Exit price for ${symbol}:`)
    if (priceStr === null) return
    const price = parseFloat(priceStr)
    if (isNaN(price) || price <= 0) { alert('Invalid price'); return }
    exit.mutate({ id, price, qty })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1000 }}>
      {data && (
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>
          {active} active · {positions.length - active} exited
        </span>
      )}

      {isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[...Array(3)].map((_, i) => <Skeleton key={i} h={60} />)}
        </div>
      ) : (
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          overflow: 'hidden',
        }}>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--muted)', fontSize: 11, borderBottom: '1px solid var(--border)' }}>
                {['Symbol', 'State', 'Avg Cost', 'Total Qty', 'Opened', 'Last Thesis Check', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map(pos => {
                const style = STATE_STYLE[pos.state] ?? STATE_STYLE.EXITED
                const isActive = pos.state === 'ACTIVE'
                const isPaused = pos.state === 'PAUSED'
                const isExited = pos.state === 'EXITED'
                return (
                  <tr key={pos.id} style={{ borderBottom: '1px solid var(--faint)' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 700 }}>{pos.symbol}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        fontSize: 11,
                        padding: '3px 8px',
                        borderRadius: 6,
                        background: style.bg,
                        color: style.color,
                        fontWeight: 600,
                      }}>
                        {pos.state}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px' }}>₹{parseFloat(pos.avg_cost).toLocaleString('en-IN')}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--muted)' }}>{pos.qty_total}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--muted)', fontSize: 12 }}>
                      {new Date(pos.opened_at).toLocaleDateString('en-IN')}
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--muted)', fontSize: 12 }}>
                      {new Date(pos.last_thesis_check_at).toLocaleDateString('en-IN')}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {!isExited && (
                        <div style={{ display: 'flex', gap: 6 }}>
                          {isActive && (
                            <button
                              onClick={() => pause.mutate(pos.id)}
                              disabled={pause.isPending}
                              title="Pause accumulation"
                              style={{
                                display: 'flex', alignItems: 'center', gap: 4,
                                padding: '5px 10px',
                                background: 'rgba(245,158,11,0.1)',
                                border: '1px solid var(--amber)',
                                borderRadius: 6, color: 'var(--amber)',
                                fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              }}>
                              <PauseIcon size={11} /> Pause
                            </button>
                          )}
                          {isPaused && (
                            <button
                              onClick={() => resume.mutate(pos.id)}
                              disabled={resume.isPending}
                              title="Resume accumulation"
                              style={{
                                display: 'flex', alignItems: 'center', gap: 4,
                                padding: '5px 10px',
                                background: 'rgba(0,200,150,0.1)',
                                border: '1px solid var(--green)',
                                borderRadius: 6, color: 'var(--green)',
                                fontSize: 11, fontWeight: 600, cursor: 'pointer',
                              }}>
                              <PlayIcon size={11} /> Resume
                            </button>
                          )}
                          <button
                            onClick={() => handleExit(pos.id, pos.symbol, pos.qty_total)}
                            disabled={exit.isPending}
                            title="Exit position"
                            style={{
                              display: 'flex', alignItems: 'center', gap: 4,
                              padding: '5px 10px',
                              background: 'var(--red-bg)',
                              border: '1px solid var(--red)',
                              borderRadius: 6, color: 'var(--red)',
                              fontSize: 11, fontWeight: 600, cursor: 'pointer',
                            }}>
                            <XIcon size={11} /> Exit
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
              {!positions.length && (
                <tr>
                  <td colSpan={7} style={{ padding: '32px 16px', textAlign: 'center', fontSize: 13, color: 'var(--dim)' }}>
                    No accumulation positions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
