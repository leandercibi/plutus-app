import { useState } from 'react'
import {
  usePortfolioSnapshot, useSwingPositions, useExitTrade, useLTP,
  useDailyHoldingsSummary, useRefreshAiSummary,
} from '../api/hooks'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { AiSummaryCard } from '../components/ui/AiSummaryCard'
import { PositionsIcon } from '../components/icons'
import type { PositionSnapshot, SwingTrade } from '../types/api'

// ── Exit modal ────────────────────────────────────────────────────────────────

const EXIT_REASONS = [
  'Target reached',
  'Stop loss hit',
  'Trailing stop hit',
  'Thesis invalidated',
  'Portfolio rebalance',
  'Manual exit',
]

function ExitModal({
  position,
  trade,
  onClose,
}: {
  position: PositionSnapshot
  trade: SwingTrade
  onClose: () => void
}) {
  const ltpQuery  = useLTP(position.symbol)
  const cmp       = ltpQuery.data ?? position.current_price   // fall back to snapshot price
  const exitTrade = useExitTrade()

  const [qty, setQty]       = useState(String(position.qty))
  const [reason, setReason] = useState(EXIT_REASONS[0])
  const [customReason, setCustomReason] = useState('')

  const qtyVal = parseInt(qty, 10)
  const isValid = !isNaN(qtyVal) && qtyVal > 0 && qtyVal <= position.qty

  const exitPrice = cmp
  const totalValue = isValid && exitPrice ? qtyVal * exitPrice : null
  const pnl = totalValue != null ? totalValue - qtyVal * position.avg_cost : null

  const finalReason = reason === 'Manual exit' && customReason.trim()
    ? customReason.trim()
    : reason

  const handleSubmit = () => {
    if (!isValid) return
    exitTrade.mutate(
      { tradeId: trade.id, reason: finalReason },
      { onSuccess: () => onClose() },
    )
  }

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
        borderRadius: 16, padding: 28, width: 440, maxWidth: '92vw',
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18 }}>{position.symbol}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3 }}>
              Exit position · {position.qty} shares held
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--muted)',
            fontSize: 18, cursor: 'pointer', padding: '0 4px', lineHeight: 1,
          }}>✕</button>
        </div>

        {/* Position summary */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
          background: 'var(--faint)', borderRadius: 10, padding: '12px 14px',
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>AVG COST</div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>₹{position.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>CMP</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--blue)' }}>
              {ltpQuery.isLoading ? '…' : `₹${cmp.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>UNREALISED P&L</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: position.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {position.pnl >= 0 ? '+' : ''}₹{position.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>

        {/* Shares to sell */}
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: 5 }}>
            SHARES TO SELL
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              value={qty}
              onChange={e => setQty(e.target.value)}
              type="number"
              min="1"
              max={position.qty}
              style={{
                flex: 1, padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)', border: `1px solid ${isValid || !qty ? 'var(--border)' : 'var(--red)'}`,
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
            <button onClick={() => setQty(String(position.qty))} style={{
              padding: '9px 14px', fontSize: 12, fontWeight: 600,
              background: 'var(--faint)', border: '1px solid var(--border)',
              borderRadius: 8, color: 'var(--muted)', cursor: 'pointer', whiteSpace: 'nowrap',
            }}>All {position.qty}</button>
          </div>
        </div>

        {/* Total value preview */}
        {isValid && exitPrice != null && (
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
            background: 'var(--faint)', borderRadius: 10, padding: '12px 14px',
          }}>
            <div>
              <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>EXIT PRICE (CMP)</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>₹{exitPrice.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>TOTAL PROCEEDS</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--blue)' }}>
                ₹{totalValue!.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </div>
            </div>
            {pnl != null && (
              <div style={{ gridColumn: '1/-1' }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>REALISED P&L (on {qtyVal} shares)</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Exit reason */}
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: 8 }}>
            EXIT REASON
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {EXIT_REASONS.map(r => (
              <button
                key={r}
                onClick={() => setReason(r)}
                style={{
                  padding: '5px 12px', borderRadius: 20, fontSize: 12, cursor: 'pointer',
                  background: reason === r ? 'rgba(242,54,69,0.12)' : 'var(--faint)',
                  border: `1px solid ${reason === r ? 'var(--red)' : 'var(--border)'}`,
                  color: reason === r ? 'var(--red)' : 'var(--muted)',
                  fontWeight: reason === r ? 700 : 400,
                }}
              >{r}</button>
            ))}
          </div>
          {reason === 'Manual exit' && (
            <input
              value={customReason}
              onChange={e => setCustomReason(e.target.value)}
              placeholder="Describe reason…"
              style={{
                width: '100%', marginTop: 8, padding: '8px 12px', fontSize: 13,
                background: 'var(--bg)', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
          )}
        </div>

        {exitTrade.isError && (
          <div style={{ fontSize: 12, color: 'var(--red)', background: 'rgba(242,54,69,0.08)', padding: '8px 12px', borderRadius: 8 }}>
            {String(exitTrade.error)}
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
            disabled={!isValid || exitTrade.isPending}
            style={{
              flex: 2, padding: '10px 0',
              background: isValid ? 'var(--red)' : 'var(--faint)',
              border: 'none', borderRadius: 10,
              color: isValid ? '#fff' : 'var(--dim)',
              fontSize: 13, fontWeight: 700,
              cursor: isValid && !exitTrade.isPending ? 'pointer' : 'default',
              opacity: exitTrade.isPending ? 0.6 : 1,
            }}
          >
            {exitTrade.isPending
              ? 'Closing…'
              : `Exit ${qtyVal || '—'} shares · ₹${totalValue?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Positions() {
  const snap   = usePortfolioSnapshot()
  const trades = useSwingPositions()
  const error  = snap.error || trades.error

  const daily = useDailyHoldingsSummary()
  const refreshDaily = useRefreshAiSummary('daily')

  const [exitTarget, setExitTarget] = useState<{ position: PositionSnapshot; trade: SwingTrade } | null>(null)

  if (error) return <ErrorBanner message={String(error)} />

  const positions = snap.data?.positions ?? []

  // Map symbol → open swing trade
  const tradeBySymbol: Record<string, SwingTrade> = {}
  for (const t of trades.data ?? []) {
    if (t.state === 'OPEN') tradeBySymbol[t.symbol] = t
  }

  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>

      {/* Main column */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1, minWidth: 0, maxWidth: 1000 }}>

      {snap.data && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>{positions.length} open positions</span>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>·</span>
          <span style={{
            fontSize: 13, fontWeight: 600,
            color: snap.data.total_pnl >= 0 ? 'var(--green)' : 'var(--red)',
          }}>
            {snap.data.total_pnl >= 0 ? '+' : ''}₹{snap.data.total_pnl.toLocaleString('en-IN')}
            {' '}({snap.data.total_pnl_pct >= 0 ? '+' : ''}{snap.data.total_pnl_pct.toFixed(2)}%)
          </span>
        </div>
      )}

      {snap.isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[...Array(3)].map((_, i) => <Skeleton key={i} h={60} />)}
        </div>
      ) : (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--muted)', fontSize: 11, borderBottom: '1px solid var(--border)' }}>
                {['Symbol', 'Mode', 'Qty', 'Avg Cost', 'CMP', 'Stop Loss', 'SL Dist', 'P&L', 'P&L %', ''].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map(p => {
                const trade    = tradeBySymbol[p.symbol]
                const pnlColor = p.pnl >= 0 ? 'var(--green)' : 'var(--red)'
                return (
                  <tr key={p.symbol} style={{ borderBottom: '1px solid var(--faint)' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 700 }}>{p.symbol}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        fontSize: 11, padding: '2px 6px', borderRadius: 4,
                        background: 'var(--faint)', color: 'var(--muted)', textTransform: 'uppercase',
                      }}>{p.mode}</span>
                    </td>
                    <td style={{ padding: '12px 16px', color: 'var(--muted)' }}>{p.qty}</td>
                    <td style={{ padding: '12px 16px' }}>₹{p.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                    <td style={{ padding: '12px 16px', fontWeight: 600 }}>₹{p.current_price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--red)' }}>₹{p.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--muted)', fontSize: 12 }}>{p.sl_distance_pct.toFixed(1)}%</td>
                    <td style={{ padding: '12px 16px', color: pnlColor, fontWeight: 600 }}>
                      {p.pnl >= 0 ? '+' : ''}₹{p.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </td>
                    <td style={{ padding: '12px 16px', color: pnlColor, fontSize: 12 }}>
                      {p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct.toFixed(1)}%
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {trade ? (
                        <button
                          onClick={() => setExitTarget({ position: p, trade })}
                          style={{
                            padding: '5px 12px',
                            background: 'rgba(242,54,69,0.1)', border: '1px solid var(--red)',
                            borderRadius: 6, color: 'var(--red)', fontSize: 11, fontWeight: 700,
                            cursor: 'pointer',
                          }}>
                          Exit
                        </button>
                      ) : (
                        <span style={{ fontSize: 11, color: 'var(--dim)' }}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
              {!positions.length && (
                <tr>
                  <td colSpan={10} style={{ padding: '32px 16px', textAlign: 'center', fontSize: 13, color: 'var(--dim)' }}>
                    No open positions
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      </div>

      {/* Sticky holdings AI rail — pinned while the table scrolls */}
      <aside style={{
        width: 340,
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        maxHeight: 'calc(100vh - 100px)',
        overflowY: 'auto',
      }}>
        <AiSummaryCard
          title="Holdings Check-In"
          subtitle="Daily AI review of your open positions"
          icon={<PositionsIcon size={13} />}
          summary={daily.data}
          isLoading={daily.isLoading}
          isError={daily.isError}
          onRefresh={() => refreshDaily.mutate()}
          isRefreshing={refreshDaily.isPending}
        />
      </aside>

      {exitTarget && (
        <ExitModal
          position={exitTarget.position}
          trade={exitTarget.trade}
          onClose={() => setExitTarget(null)}
        />
      )}
    </div>
  )
}
