import { useCalibration } from '../api/hooks'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'

const SPRT_COLOR: Record<string, string> = {
  'accept_H1': 'var(--green)',
  'accept_H0': 'var(--red)',
  'continue': 'var(--amber)',
}

export default function Calibration() {
  const { data, isLoading, error } = useCalibration()

  if (error) return <ErrorBanner message={String(error)} />

  return (
    <div className="flex flex-col gap-4 max-w-4xl">
      <div>
        <h1 className="text-xl font-semibold">Calibration</h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--muted)' }}>
          SPRT test state and expectancy per score bucket × regime
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {[...Array(4)].map((_, i) => <Skeleton key={i} h={180} />)}
        </div>
      ) : (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
             className="rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: 'var(--muted)', fontSize: 11, borderColor: 'var(--border)' }} className="border-b">
                {['Bucket', 'Regime', 'N', 'Win Rate', 'E[R]', 'CI', 'Confidence', 'SPRT', 'Updated'].map(h => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((row, i) => {
                const sprtColor = SPRT_COLOR[row.sprt_state] ?? 'var(--dim)'
                return (
                  <tr key={i} className="border-b" style={{ borderColor: 'var(--faint)' }}>
                    <td className="px-4 py-3 font-mono text-xs">{row.bucket}</td>
                    <td className="px-4 py-3">{row.regime}</td>
                    <td className="px-4 py-3">{row.n_closed}</td>
                    <td className="px-4 py-3">{(row.win_rate * 100).toFixed(0)}%</td>
                    <td className="px-4 py-3"
                        style={{ color: row.expectancy_R >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      {row.expectancy_R.toFixed(2)}R
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--muted)', fontSize: 11 }}>
                      [{row.ci_low_R.toFixed(2)}, {row.ci_high_R.toFixed(2)}]
                    </td>
                    <td className="px-4 py-3">{row.confidence_band}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded"
                            style={{ background: 'var(--faint)', color: sprtColor }}>
                        {row.sprt_state}
                      </span>
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--muted)', fontSize: 11 }}>
                      {new Date(row.last_updated).toLocaleDateString('en-IN')}
                    </td>
                  </tr>
                )
              })}
              {!data?.length && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-sm" style={{ color: 'var(--dim)' }}>
                  No calibration data yet.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
