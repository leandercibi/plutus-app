import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'

interface PostmortemData {
  week_ending: string
  swing_return_pct: number
  nifty_return_pct: number
  regime_switched_return_pct: number
  random_baseline_return_pct: number
  n_swing_trades_closed: number
  drawdown_pct: number
  report_md_path: string | null
}

function ReturnCard({ label, value, compare }: { label: string; value: number; compare?: number }) {
  const beat = compare !== undefined ? value > compare : value >= 0
  const color = beat ? 'var(--green)' : 'var(--red)'
  return (
    <div style={{ background: 'var(--bg)', borderRadius: 8, padding: '12px 16px' }}>
      <p className="text-xs" style={{ color: 'var(--muted)' }}>{label}</p>
      <p className="text-2xl font-bold mt-0.5" style={{ color }}>
        {value >= 0 ? '+' : ''}{value.toFixed(2)}%
      </p>
    </div>
  )
}

export default function Postmortem() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['postmortem'],
    queryFn: () => apiClient.get<PostmortemData>('/swing/postmortem/latest').then(r => r.data),
  })

  if (error) return <ErrorBanner message={String(error)} />

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <h1 className="text-xl font-semibold">Weekly Postmortem</h1>

      {isLoading ? (
        <div className="flex flex-col gap-3">{[...Array(4)].map((_, i) => <Skeleton key={i} h={80} />)}</div>
      ) : data ? (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
             className="rounded-xl p-5 flex flex-col gap-4">
          <p className="text-xs" style={{ color: 'var(--muted)' }}>
            Week ending {new Date(data.week_ending).toLocaleDateString('en-IN')} ·{' '}
            {data.n_swing_trades_closed} trades closed
          </p>

          <div className="grid grid-cols-2 gap-3">
            <ReturnCard label="Plutus return" value={data.swing_return_pct}
              compare={data.nifty_return_pct} />
            <ReturnCard label="Nifty 50" value={data.nifty_return_pct} />
            <ReturnCard label="Regime-switched" value={data.regime_switched_return_pct} />
            <ReturnCard label="Random baseline" value={data.random_baseline_return_pct} />
          </div>

          <div style={{ background: 'var(--bg)', borderRadius: 8, padding: '12px 16px' }}>
            <p className="text-xs" style={{ color: 'var(--muted)' }}>Max Drawdown</p>
            <p className="text-2xl font-bold mt-0.5" style={{ color: 'var(--red)' }}>
              -{data.drawdown_pct.toFixed(2)}%
            </p>
          </div>

          {data.swing_return_pct > data.nifty_return_pct && (
            <p className="text-sm" style={{ color: 'var(--green)' }}>
              ✓ Beat Nifty by {(data.swing_return_pct - data.nifty_return_pct).toFixed(2)}%
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm" style={{ color: 'var(--dim)' }}>No postmortem data yet.</p>
      )}
    </div>
  )
}
