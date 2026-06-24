import { useState, useMemo, useEffect } from 'react'
import {
  useCandidates,
  useStartAccumulationPosition,
  useAccumulationPositions,
  useLTP,
} from '../api/hooks'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import type { AccumulationCandidate, AccumulationPosition } from '../types/api'

// ── RS percentile bar ────────────────────────────────────────────────────────

function RSBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(100, Math.max(0, value * 100))
  const color = pct >= 60 ? 'var(--green)' : pct >= 30 ? 'var(--amber)' : 'var(--red)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--muted)' }}>
        <span>{label}</span>
        <span style={{ color }}>{pct.toFixed(0)}th</span>
      </div>
      <div style={{ background: 'var(--faint)', borderRadius: 3, height: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, background: color, height: '100%', borderRadius: 3 }} />
      </div>
    </div>
  )
}

// ── Accumulation modal ───────────────────────────────────────────────────────

function AccumModal({
  candidate,
  positions,
  onClose,
}: {
  candidate: AccumulationCandidate
  positions: AccumulationPosition[]
  onClose: () => void
}) {
  const priceQuery = useLTP(candidate.symbol)
  const cmp = priceQuery.data ?? null

  const [price, setPrice] = useState('')
  const [qty, setQty] = useState('')
  const [note, setNote] = useState('')

  const startPos = useStartAccumulationPosition()

  // Pre-fill price with CMP once loaded
  useEffect(() => {
    if (cmp != null && price === '') setPrice(cmp.toFixed(2))
  }, [cmp])

  const existing = positions.filter(p => p.symbol === candidate.symbol && p.state !== 'CLOSED')
  const trancheNum = existing.length + 1

  const priceVal = parseFloat(price)
  const qtyVal   = parseInt(qty, 10)
  const isValid  = !isNaN(priceVal) && priceVal > 0 && !isNaN(qtyVal) && qtyVal > 0

  const handleSubmit = () => {
    if (!isValid) return
    startPos.mutate(
      { symbol: candidate.symbol, price: priceVal, qty: qtyVal, note: note.trim() || undefined },
      { onSuccess: () => onClose() },
    )
  }

  // Close on backdrop click
  const handleBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose()
  }

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
        borderRadius: 16, padding: 28, width: 420, maxWidth: '92vw',
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18 }}>{candidate.symbol}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3 }}>
              Score <strong style={{ color: 'var(--green)' }}>{candidate.score}/100</strong>
              {candidate.thesis_text && ` · ${candidate.thesis_text}`}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: 'var(--muted)',
              fontSize: 18, cursor: 'pointer', padding: '0 4px', lineHeight: 1,
            }}
          >✕</button>
        </div>

        {/* CMP */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          background: 'var(--faint)', borderRadius: 10, padding: '10px 14px',
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>CURRENT MARKET PRICE</div>
            {priceQuery.isLoading ? (
              <div style={{ fontSize: 13, color: 'var(--dim)' }}>Fetching…</div>
            ) : cmp != null ? (
              <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>
                ₹{cmp.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            ) : (
              <div style={{ fontSize: 13, color: 'var(--dim)' }}>Unavailable</div>
            )}
          </div>
          {cmp != null && (
            <button
              onClick={() => setPrice(cmp.toFixed(2))}
              style={{
                fontSize: 11, padding: '4px 10px',
                background: 'rgba(0,200,150,0.1)', border: '1px solid var(--green)',
                borderRadius: 6, color: 'var(--green)', cursor: 'pointer',
              }}
            >Use CMP</button>
          )}
        </div>

        {/* Existing open positions */}
        {existing.length > 0 && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.05em' }}>
              EXISTING OPEN POSITIONS
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {existing.map((p, i) => (
                <div key={p.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  background: 'var(--faint)', borderRadius: 8, padding: '8px 12px',
                }}>
                  <div style={{ fontSize: 12 }}>
                    <span style={{ color: 'var(--muted)' }}>Position {i + 1} — </span>
                    <strong>{p.qty_total}</strong> shares
                    <span style={{ color: 'var(--muted)' }}> @ avg ₹{parseFloat(p.avg_cost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                  </div>
                  <span style={{
                    fontSize: 10, padding: '2px 7px', borderRadius: 4,
                    background: p.state === 'ACTIVE' ? 'rgba(0,200,150,0.1)' : 'rgba(245,158,11,0.1)',
                    color: p.state === 'ACTIVE' ? 'var(--green)' : 'var(--amber)',
                    fontWeight: 700,
                  }}>{p.state}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tranche label */}
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--blue)',
          borderTop: '1px solid var(--border)', paddingTop: 16,
        }}>
          This will be Tranche {trancheNum}
        </div>

        {/* Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, display: 'block', marginBottom: 5 }}>
              ENTRY PRICE (₹)
            </label>
            <input
              value={price}
              onChange={e => setPrice(e.target.value)}
              placeholder="e.g. 5234.50"
              style={{
                width: '100%', padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, display: 'block', marginBottom: 5 }}>
              SHARES
            </label>
            <input
              value={qty}
              onChange={e => setQty(e.target.value)}
              placeholder="e.g. 10"
              type="number"
              min="1"
              style={{
                width: '100%', padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, display: 'block', marginBottom: 5 }}>
              NOTE (optional)
            </label>
            <input
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="e.g. First tranche on support"
              style={{
                width: '100%', padding: '9px 12px', fontSize: 13,
                background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={onClose}
            style={{
              flex: 1, padding: '10px 0',
              background: 'transparent', border: '1px solid var(--border)',
              borderRadius: 10, color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
            }}
          >Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || startPos.isPending}
            style={{
              flex: 2, padding: '10px 0',
              background: isValid ? 'var(--green)' : 'var(--faint)',
              border: 'none', borderRadius: 10,
              color: isValid ? '#000' : 'var(--dim)',
              fontSize: 13, fontWeight: 700, cursor: isValid ? 'pointer' : 'default',
              opacity: startPos.isPending ? 0.6 : 1,
            }}
          >
            {startPos.isPending ? 'Submitting…' : `Start Tranche ${trancheNum}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Candidate card ───────────────────────────────────────────────────────────

function CandidateCard({
  candidate,
  onAccumulate,
}: {
  candidate: AccumulationCandidate
  onAccumulate: () => void
}) {
  const c = candidate
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderLeft: `3px solid ${c.hard_avoid_active ? 'var(--red)' : 'var(--green)'}`,
      borderRadius: 12, padding: 16,
      display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 15 }}>{c.symbol}</span>
            {c.hard_avoid_active && (
              <span style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                background: 'var(--red-bg)', color: 'var(--red)', fontWeight: 700,
              }}>Hard Avoid</span>
            )}
          </div>
          <div style={{ fontSize: 11, color: 'var(--dim)', marginTop: 2 }}>
            {new Date(c.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--green)' }}>{c.score}</div>
          <div style={{ fontSize: 10, color: 'var(--dim)' }}>/100</div>
        </div>
      </div>

      {/* RS bars — with header explaining what %ile means */}
      <div>
        <div style={{
          fontSize: 10, color: 'var(--dim)', marginBottom: 6,
          display: 'flex', justifyContent: 'space-between',
        }}>
          <span>RELATIVE STRENGTH vs NSE 500</span>
          <span>PERCENTILE RANK</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <RSBar label="30 day" value={c.rs_30} />
          <RSBar label="90 day" value={c.rs_90} />
          <RSBar label="180 day" value={c.rs_180} />
        </div>
      </div>

      {/* Thesis */}
      {c.thesis_text && (
        <p style={{ fontSize: 11, color: 'var(--dim)', lineHeight: 1.5, margin: 0 }}>
          {c.thesis_text}
        </p>
      )}

      {/* Action */}
      {!c.hard_avoid_active && (
        <button
          onClick={onAccumulate}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            padding: '8px 0',
            background: 'rgba(0,200,150,0.1)',
            border: '1px solid var(--green)',
            borderRadius: 8,
            color: 'var(--green)',
            fontSize: 12, fontWeight: 700, cursor: 'pointer',
          }}
        >
          + Start / Add Tranche
        </button>
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Candidates() {
  const { data, isLoading, error } = useCandidates()
  const { data: positions = [] } = useAccumulationPositions()

  const [modalCandidate, setModalCandidate] = useState<AccumulationCandidate | null>(null)

  // Deduplicate by symbol — keep the latest (highest created_at) per symbol, then sort by score
  const deduped = useMemo(() => {
    if (!data) return []
    const best = new Map<string, AccumulationCandidate>()
    for (const c of data) {
      const prev = best.get(c.symbol)
      if (!prev || c.created_at > prev.created_at) best.set(c.symbol, c)
    }
    return [...best.values()].sort((a, b) => b.score - a.score)
  }, [data])

  if (error) return <ErrorBanner message={String(error)} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 960 }}>
      <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
        {isLoading
          ? 'Loading…'
          : `${deduped.length} candidates · sorted by score · deduplicated by symbol`}
      </p>

      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
          {[...Array(6)].map((_, i) => <Skeleton key={i} h={200} />)}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
          {deduped.map(c => (
            <CandidateCard
              key={c.symbol}
              candidate={c}
              onAccumulate={() => setModalCandidate(c)}
            />
          ))}
          {!deduped.length && (
            <p style={{ fontSize: 13, color: 'var(--dim)', gridColumn: '1/-1', padding: '32px 0', textAlign: 'center' }}>
              No candidates found. Run the Sunday pipeline to screen.
            </p>
          )}
        </div>
      )}

      {modalCandidate && (
        <AccumModal
          candidate={modalCandidate}
          positions={positions}
          onClose={() => setModalCandidate(null)}
        />
      )}
    </div>
  )
}
