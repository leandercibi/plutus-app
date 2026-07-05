import { RefreshIcon } from '../icons'
import { Skeleton } from './Skeleton'
import type { SignalNews, NewsItem } from '../../types/api'

interface Props {
  data: SignalNews | undefined
  isLoading: boolean
  isError: boolean
  onRefresh: () => void
  isRefreshing: boolean
}

const SENTIMENT: Record<string, { color: string; bg: string; label: string }> = {
  positive: { color: 'var(--green)', bg: 'var(--green-bg)', label: 'Positive' },
  negative: { color: 'var(--red)', bg: 'var(--red-bg)', label: 'Negative' },
  neutral: { color: 'var(--muted)', bg: 'var(--faint)', label: 'Neutral' },
}

function relTime(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const mins = Math.round((Date.now() - t) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.round(hrs / 24)
  return `${days}d ago`
}

export function SignalNewsWidget({ data, isLoading, isError, onRefresh, isRefreshing }: Props) {
  const items = data?.items ?? []

  // Group articles by sector, ordered by the backend's top-sector ranking.
  const grouped: { sector: string; items: NewsItem[] }[] = (() => {
    const bySector = new Map<string, NewsItem[]>()
    for (const it of items) {
      const key = it.sector ?? 'Other'
      const arr = bySector.get(key) ?? []
      arr.push(it)
      bySector.set(key, arr)
    }
    const order = data?.sectors ?? []
    const ordered = [
      ...order.filter(s => bySector.has(s)),
      ...[...bySector.keys()].filter(k => !order.includes(k)),
    ]
    return ordered.map(k => ({ sector: k, items: bySector.get(k) ?? [] }))
  })()

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Signal Stock News</span>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', padding: '1px 6px',
              borderRadius: 4, background: 'var(--amber-bg)', color: 'var(--amber)',
            }}>LIVE</span>
          </div>
          {data?.sectors?.length ? (
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>
              Top sectors: {data.sectors.join(' · ')}
            </div>
          ) : null}
        </div>
        <button
          onClick={onRefresh}
          disabled={isRefreshing || isLoading}
          title="Refresh news"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            background: 'transparent', border: '1px solid var(--border)', borderRadius: 7,
            color: 'var(--muted)', fontSize: 11, padding: '4px 8px',
            cursor: isRefreshing || isLoading ? 'default' : 'pointer', opacity: isRefreshing || isLoading ? 0.5 : 1,
          }}
        >
          <span style={{ display: 'inline-flex', animation: isRefreshing ? 'plutus-spin 0.9s linear infinite' : undefined }}>
            <RefreshIcon size={12} />
          </span>
          {isRefreshing ? 'Fetching…' : 'Refresh'}
        </button>
      </div>

      {/* Body */}
      {isLoading ? (
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[...Array(3)].map((_, i) => <Skeleton key={i} h={40} />)}
        </div>
      ) : data && !data.available ? (
        <p style={{ padding: '16px', fontSize: 13, color: 'var(--dim)', margin: 0, lineHeight: 1.55 }}>
          News is off. Set <code style={{ background: 'var(--faint)', padding: '1px 4px', borderRadius: 4 }}>MARKETAUX_API_KEY</code> in the backend env to show live headlines for your signal stocks.
        </p>
      ) : isError ? (
        <div style={{ padding: '16px' }}>
          <p style={{ fontSize: 13, color: 'var(--red)', margin: 0 }}>Couldn't load news right now.</p>
          <button onClick={onRefresh} style={{ marginTop: 6, fontSize: 12, color: 'var(--blue)', background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}>Try again</button>
        </div>
      ) : items.length === 0 ? (
        <p style={{ padding: '20px 16px', textAlign: 'center', fontSize: 13, color: 'var(--dim)', margin: 0 }}>
          No recent sector news found for your signals.
        </p>
      ) : (
        <div>
          {grouped.map(group => (
            <div key={group.sector}>
              {/* Sector header */}
              <div style={{
                padding: '7px 16px', background: 'var(--faint)',
                borderTop: '1px solid var(--border)',
                fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
                textTransform: 'uppercase', color: 'var(--muted)',
                display: 'flex', justifyContent: 'space-between',
              }}>
                <span>{group.sector}</span>
                <span style={{ color: 'var(--dim)' }}>{group.items.length}</span>
              </div>
              {group.items.map((it, i) => {
                const s = SENTIMENT[it.sentiment] ?? SENTIMENT.neutral
                return (
                  <a
                    key={`${it.url}-${i}`}
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'block', padding: '11px 16px', borderTop: '1px solid var(--faint)',
                      textDecoration: 'none', color: 'inherit',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                      {it.symbol ? (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4,
                          background: 'var(--blue-bg)', color: 'var(--blue)',
                        }}>{it.symbol}</span>
                      ) : null}
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 4,
                        background: s.bg, color: s.color,
                      }}>{s.label}</span>
                      <span style={{ flex: 1 }} />
                      <span style={{ fontSize: 10, color: 'var(--dim)' }}>{relTime(it.published_at)}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.4 }}>{it.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{it.source}</div>
                  </a>
                )
              })}
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      {data?.available && items.length > 0 && (
        <div style={{ padding: '8px 16px', borderTop: '1px solid var(--faint)', fontSize: 10, color: 'var(--dim)', display: 'flex', justifyContent: 'space-between' }}>
          <span>via Marketaux{data.cached ? ' · cached' : ''}</span>
          <span>updated {relTime(data.fetched_at)}</span>
        </div>
      )}
    </div>
  )
}
