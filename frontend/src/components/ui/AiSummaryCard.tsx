import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { RefreshIcon } from '../icons'
import { Skeleton } from './Skeleton'
import type { AiSummary } from '../../types/api'

interface Props {
  title: string
  icon?: ReactNode
  summary: AiSummary | undefined
  isLoading: boolean
  isError: boolean
  onRefresh: () => void
  isRefreshing: boolean
  /** Optional hint shown under the title, e.g. "for the week of …". */
  subtitle?: string
}

// ── Minimal markdown → React (bold, bullets, headings) ─────────────
function renderInline(text: string, keyBase: string): ReactNode[] {
  // Split on **bold** spans, keeping the delimiters' content.
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyBase}-${i}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${keyBase}-${i}`}>{part}</span>
  })
}

function renderMarkdown(md: string): ReactNode {
  const lines = md.replace(/\r/g, '').split('\n')
  const blocks: ReactNode[] = []
  let bullets: string[] = []

  const flushBullets = () => {
    if (bullets.length === 0) return
    const items = bullets
    blocks.push(
      <ul key={`ul-${blocks.length}`} style={{ margin: '4px 0 8px', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.map((b, i) => (
          <li key={i} style={{ fontSize: 13, lineHeight: 1.5 }}>{renderInline(b, `li-${blocks.length}-${i}`)}</li>
        ))}
      </ul>,
    )
    bullets = []
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    const trimmed = line.trim()
    if (!trimmed) { flushBullets(); continue }

    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/)
    if (bulletMatch) { bullets.push(bulletMatch[1]); continue }

    flushBullets()
    const headingMatch = trimmed.match(/^#{1,4}\s+(.*)$/)
    if (headingMatch) {
      blocks.push(
        <div key={`h-${blocks.length}`} style={{ fontSize: 13, fontWeight: 700, margin: '8px 0 2px' }}>
          {renderInline(headingMatch[1], `h-${blocks.length}`)}
        </div>,
      )
      continue
    }
    blocks.push(
      <p key={`p-${blocks.length}`} style={{ fontSize: 13, lineHeight: 1.55, margin: '4px 0' }}>
        {renderInline(trimmed, `p-${blocks.length}`)}
      </p>,
    )
  }
  flushBullets()
  return blocks
}

export function AiSummaryCard({
  title, icon, summary, isLoading, isError, onRefresh, isRefreshing, subtitle,
}: Props) {
  const body = useMemo(
    () => (summary?.content ? renderMarkdown(summary.content) : null),
    [summary?.content],
  )

  const ts = summary?.created_at
    ? new Date(summary.created_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })
    : null

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 22, height: 22, borderRadius: 6, background: 'var(--blue-bg)', color: 'var(--blue)',
        }}>{icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: '0.06em', padding: '1px 6px',
              borderRadius: 4, background: 'var(--blue-bg)', color: 'var(--blue)',
            }}>AI</span>
          </div>
          {subtitle && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>{subtitle}</div>}
        </div>
        <button
          onClick={onRefresh}
          disabled={isRefreshing || isLoading}
          title="Regenerate summary"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            background: 'transparent', border: '1px solid var(--border)', borderRadius: 7,
            color: 'var(--muted)', fontSize: 11, padding: '4px 8px',
            cursor: isRefreshing || isLoading ? 'default' : 'pointer', opacity: isRefreshing || isLoading ? 0.5 : 1,
          }}
        >
          <span style={{
            display: 'inline-flex',
            animation: isRefreshing ? 'plutus-spin 0.9s linear infinite' : undefined,
          }}>
            <RefreshIcon size={12} />
          </span>
          {isRefreshing ? 'Thinking…' : 'Regenerate'}
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: '12px 16px' }}>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[...Array(3)].map((_, i) => <Skeleton key={i} h={14} />)}
          </div>
        ) : summary && !summary.available ? (
          <p style={{ fontSize: 13, color: 'var(--dim)', margin: 0, lineHeight: 1.55 }}>
            AI summaries are off. Set <code style={{ background: 'var(--faint)', padding: '1px 4px', borderRadius: 4 }}>OPENROUTER_API_KEY</code> (and optionally <code style={{ background: 'var(--faint)', padding: '1px 4px', borderRadius: 4 }}>LLM_MODEL</code>) in the backend env to enable them.
          </p>
        ) : isError ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <p style={{ fontSize: 13, color: 'var(--red)', margin: 0 }}>Couldn't generate this summary right now.</p>
            <button onClick={onRefresh} style={{ alignSelf: 'flex-start', fontSize: 12, color: 'var(--blue)', background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}>
              Try again
            </button>
          </div>
        ) : body ? (
          <div>{body}</div>
        ) : (
          <p style={{ fontSize: 13, color: 'var(--dim)', margin: 0 }}>No summary available yet.</p>
        )}
      </div>

      {/* Footer */}
      {summary?.available && ts && !isLoading && (
        <div style={{ padding: '8px 16px', borderTop: '1px solid var(--faint)', fontSize: 10, color: 'var(--dim)', display: 'flex', justifyContent: 'space-between' }}>
          <span>{summary.model}</span>
          <span>{summary.cached ? 'cached · ' : ''}{ts}</span>
        </div>
      )}
    </div>
  )
}
