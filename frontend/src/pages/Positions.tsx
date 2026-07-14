import { useState, useMemo, type CSSProperties, type ReactNode } from 'react'
import {
  usePortfolioSnapshot, useSwingPositions, useExitTrade, useLTP,
  useDailyHoldingsSummary, useRefreshAiSummary,
} from '../api/hooks'
import { Skeleton } from '../components/ui/Skeleton'
import { ErrorBanner } from '../components/ui/ErrorBanner'
import { AiSummaryCard } from '../components/ui/AiSummaryCard'
import { PositionsIcon } from '../components/icons'
import {
  useChartPanel, ChartPanelBody, DaysControl, OverlayControls,
  DEFAULT_CHART_INDICATORS, type ChartIndicators,
} from '../components/chart/ChartPanel'
import type { PositionSnapshot } from '../types/api'

// ── Hover-aware button ────────────────────────────────────────────────────────

function HoverButton({
  onClick, disabled, title, children, style, hoverStyle, activeStyle,
}: {
  onClick?: () => void
  disabled?: boolean
  title?: string
  children: ReactNode
  style: CSSProperties
  hoverStyle?: CSSProperties
  activeStyle?: CSSProperties
}) {
  const [hover, setHover] = useState(false)
  const [pressed, setPressed] = useState(false)
  const merged: CSSProperties = {
    ...style,
    ...(hover && !disabled ? hoverStyle : null),
    ...(pressed && !disabled ? activeStyle : null),
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background 120ms ease, border-color 120ms ease, filter 120ms ease',
  }
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={merged}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPressed(false) }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
    >{children}</button>
  )
}

const SELL_BUTTON_BASE: CSSProperties = {
  padding: '5px 12px',
  background: 'rgba(242,54,69,0.1)', border: '1px solid var(--red)',
  borderRadius: 6, color: 'var(--red)', fontSize: 11, fontWeight: 700,
}
const SELL_BUTTON_HOVER: CSSProperties = { background: 'rgba(242,54,69,0.22)' }
const SELL_BUTTON_ACTIVE: CSSProperties = { background: 'rgba(242,54,69,0.35)', filter: 'brightness(0.95)' }

// ── Aggregation ───────────────────────────────────────────────────────────────

type AggregatedPosition = {
  symbol: string
  mode: string
  qty: number
  avg_cost: number             // weighted by lot qty
  current_price: number
  invested: number
  pnl: number                  // sum of lot pnls (₹)
  pnl_pct: number              // weighted by invested
  stop_loss: number | null     // tightest SL across lots
  sl_distance_pct: number | null
  lots: PositionSnapshot[]     // sorted oldest → newest for FIFO
}

function aggregate(positions: PositionSnapshot[]): AggregatedPosition[] {
  const groups = new Map<string, PositionSnapshot[]>()
  for (const p of positions) {
    const key = `${p.symbol}|${p.mode}`
    const existing = groups.get(key)
    if (existing) existing.push(p)
    else groups.set(key, [p])
  }

  const out: AggregatedPosition[] = []
  for (const rawLots of groups.values()) {
    // Sort lots oldest → newest so downstream FIFO logic + history rendering
    // are consistent. Lots without opened_at sink to the bottom.
    const lots = [...rawLots].sort((a, b) => {
      const at = a.opened_at ? new Date(a.opened_at).getTime() : Number.POSITIVE_INFINITY
      const bt = b.opened_at ? new Date(b.opened_at).getTime() : Number.POSITIVE_INFINITY
      return at - bt
    })
    const qty = lots.reduce((s, l) => s + l.qty, 0)
    const invested = lots.reduce((s, l) => s + l.avg_cost * l.qty, 0)
    const current_price = lots[0].current_price
    const pnl = lots.reduce((s, l) => s + l.pnl, 0)
    const avg_cost = qty > 0 ? invested / qty : 0
    const pnl_pct = invested > 0 ? (pnl / invested) * 100 : 0

    const sls = lots.map(l => l.stop_loss).filter((v): v is number => v != null)
    const stop_loss = sls.length ? Math.max(...sls) : null
    const sl_distance_pct = stop_loss != null && current_price > 0
      ? ((current_price - stop_loss) / current_price) * 100
      : null

    out.push({
      symbol: lots[0].symbol,
      mode: lots[0].mode,
      qty,
      avg_cost,
      current_price,
      invested,
      pnl,
      pnl_pct,
      stop_loss,
      sl_distance_pct,
      lots,
    })
  }
  out.sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))
  return out
}

// ── Sell modal (single unified flow for single- and multi-lot) ────────────────

const EXIT_REASONS = [
  'Target reached',
  'Stop loss hit',
  'Trailing stop hit',
  'Thesis invalidated',
  'Portfolio rebalance',
  'Manual exit',
]

/** Given an aggregated position and a total qty the user wants to sell,
 * return the per-lot slice plan using FIFO (oldest lot first). Emits one
 * entry per lot that will be touched; each carries the lot ref, the qty
 * being sold from that lot, and whether it closes the lot fully. */
function planFifoSell(agg: AggregatedPosition, sellQty: number): { lot: PositionSnapshot; qty: number; full: boolean }[] {
  const plan: { lot: PositionSnapshot; qty: number; full: boolean }[] = []
  let remaining = sellQty
  for (const lot of agg.lots) {
    if (remaining <= 0) break
    if (lot.trade_id == null) continue   // can't sell what has no trade ref
    const take = Math.min(lot.qty, remaining)
    plan.push({ lot, qty: take, full: take === lot.qty })
    remaining -= take
  }
  return plan
}

function SellModal({
  agg,
  onClose,
}: {
  agg: AggregatedPosition
  onClose: () => void
}) {
  const ltpQuery  = useLTP(agg.symbol)
  const cmp       = ltpQuery.data ?? agg.current_price
  const exitTrade = useExitTrade()

  const [qty, setQty]       = useState(String(agg.qty))
  const [reason, setReason] = useState(EXIT_REASONS[0])
  const [customReason, setCustomReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const qtyVal = parseInt(qty, 10)
  const isValid = !isNaN(qtyVal) && qtyVal > 0 && qtyVal <= agg.qty
  const isPartial = isValid && qtyVal < agg.qty
  const isMultiLot = agg.lots.length > 1

  const plan = useMemo(() => (isValid ? planFifoSell(agg, qtyVal) : []), [agg, qtyVal, isValid])

  const exitPrice = cmp
  const totalValue = isValid && exitPrice ? qtyVal * exitPrice : null
  // Weighted realised P&L on the sliced qty, using per-lot avg costs.
  const plannedInvested = plan.reduce((s, p) => s + p.qty * p.lot.avg_cost, 0)
  const pnl = totalValue != null ? totalValue - plannedInvested : null

  const finalReason = reason === 'Manual exit' && customReason.trim()
    ? customReason.trim()
    : reason

  const handleSubmit = async () => {
    if (!isValid || plan.length === 0) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      // Sequential: each mutation invalidates portfolio-snapshot and mutates
      // trade.qty on the backend; parallel would race on stale reads.
      for (const step of plan) {
        const tid = step.lot.trade_id
        if (tid == null) continue
        await new Promise<void>((resolve, reject) => {
          exitTrade.mutate(
            { tradeId: tid, reason: finalReason, qty: step.full ? undefined : step.qty },
            { onSuccess: () => resolve(), onError: err => reject(err) },
          )
        })
      }
      onClose()
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && !submitting) onClose()
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
        borderRadius: 16, padding: 28, width: 500, maxWidth: '92vw',
        maxHeight: '92vh', overflowY: 'auto',
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18 }}>{agg.symbol}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3 }}>
              {isPartial ? 'Partial sell' : 'Full exit'}
              {' · '}{agg.qty} shares across {agg.lots.length} lot{agg.lots.length !== 1 ? 's' : ''}
              {isMultiLot && (
                <span style={{ color: 'var(--dim)' }}> · FIFO (oldest first)</span>
              )}
            </div>
          </div>
          <button onClick={onClose} disabled={submitting} style={{
            background: 'transparent', border: 'none', color: 'var(--muted)',
            fontSize: 18, cursor: submitting ? 'default' : 'pointer', padding: '0 4px', lineHeight: 1,
          }}>✕</button>
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
          background: 'var(--faint)', borderRadius: 10, padding: '12px 14px',
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>AVG COST</div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>
              ₹{agg.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>CMP</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--blue)' }}>
              {ltpQuery.isLoading ? '…' : `₹${cmp.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>TOTAL P&L</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: agg.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {agg.pnl >= 0 ? '+' : ''}₹{agg.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </div>
          </div>
        </div>

        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: 5 }}>
            SHARES TO SELL
          </label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              value={qty}
              onChange={e => setQty(e.target.value)}
              type="number"
              min="1"
              max={agg.qty}
              style={{
                flex: 1, padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)',
                border: `1px solid ${isValid || !qty ? 'var(--border)' : 'var(--red)'}`,
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
            <HoverButton
              onClick={() => setQty(String(agg.qty))}
              style={{
                padding: '9px 14px', fontSize: 12, fontWeight: 600,
                whiteSpace: 'nowrap', borderRadius: 8,
                border: qtyVal === agg.qty ? '1px solid var(--green)' : '1px solid var(--border)',
                background: qtyVal === agg.qty ? 'rgba(0,200,150,0.18)' : 'var(--faint)',
                color: qtyVal === agg.qty ? 'var(--green)' : 'var(--muted)',
              }}
              hoverStyle={qtyVal === agg.qty
                ? { background: 'rgba(0,200,150,0.28)' }
                : { background: 'var(--border)' }}
              activeStyle={{ filter: 'brightness(0.92)' }}
            >
              {qtyVal === agg.qty ? `✓ All ${agg.qty}` : `All ${agg.qty}`}
            </HoverButton>
          </div>
          {isValid && (
            <input
              type="range"
              min={1}
              max={agg.qty}
              value={qtyVal}
              onChange={e => setQty(e.target.value)}
              style={{ width: '100%', marginTop: 8 }}
            />
          )}
        </div>

        {isValid && exitPrice != null && (
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
            background: 'var(--faint)', borderRadius: 10, padding: '12px 14px',
          }}>
            <div>
              <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>EXIT PRICE (CMP)</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                ₹{exitPrice.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>TOTAL PROCEEDS</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--blue)' }}>
                ₹{totalValue!.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </div>
            </div>
            {pnl != null && (
              <div style={{ gridColumn: '1/-1' }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>
                  REALISED P&L (on {qtyVal} shares, FIFO cost basis)
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </div>
              </div>
            )}
            {isPartial && (
              <div style={{ gridColumn: '1/-1', fontSize: 11, color: 'var(--amber)' }}>
                Partial: {agg.qty - qtyVal} shares will remain.
              </div>
            )}
          </div>
        )}

        {isMultiLot && plan.length > 0 && (
          <div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6, letterSpacing: '0.05em' }}>
              FIFO SLICE PLAN
            </div>
            <div style={{
              background: 'var(--bg)', border: '1px solid var(--border)',
              borderRadius: 8, overflow: 'hidden', fontSize: 12,
            }}>
              {plan.map((p, i) => (
                <div key={p.lot.trade_id ?? i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '7px 12px',
                  borderTop: i === 0 ? 'none' : '1px solid var(--faint)',
                }}>
                  <span style={{ color: 'var(--muted)' }}>
                    Lot {agg.lots.indexOf(p.lot) + 1}
                    {p.lot.opened_at && (
                      <span style={{ color: 'var(--dim)' }}>
                        {' · '}{new Date(p.lot.opened_at).toLocaleDateString('en-IN', {
                          day: 'numeric', month: 'short',
                        })}
                      </span>
                    )}
                    {' · '}₹{p.lot.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                  </span>
                  <span style={{ color: p.full ? 'var(--red)' : 'var(--amber)', fontWeight: 600 }}>
                    {p.full ? `Close all ${p.qty}` : `Sell ${p.qty} of ${p.lot.qty}`}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: 8 }}>
            REASON
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

        {submitError && (
          <div style={{ fontSize: 12, color: 'var(--red)', background: 'rgba(242,54,69,0.08)', padding: '8px 12px', borderRadius: 8 }}>
            {submitError}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose} disabled={submitting} style={{
            flex: 1, padding: '10px 0',
            background: 'transparent', border: '1px solid var(--border)',
            borderRadius: 10, color: 'var(--muted)', fontSize: 13, cursor: submitting ? 'default' : 'pointer',
          }}>Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || submitting}
            style={{
              flex: 2, padding: '10px 0',
              background: isValid ? 'var(--red)' : 'var(--faint)',
              border: 'none', borderRadius: 10,
              color: isValid ? '#fff' : 'var(--dim)',
              fontSize: 13, fontWeight: 700,
              cursor: isValid && !submitting ? 'pointer' : 'default',
              opacity: submitting ? 0.6 : 1,
            }}
          >
            {submitting
              ? (isPartial ? 'Selling…' : 'Closing…')
              : `${isPartial ? 'Sell' : 'Exit'} ${qtyVal || '—'} shares · ₹${totalValue?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Aggregated row (with bottom chevron + expandable detail) ──────────────────

function AggregatedRow({
  agg,
  days,
  indicators,
  onSell,
  colSpan,
}: {
  agg: AggregatedPosition
  days: number
  indicators: ChartIndicators
  onSell: () => void
  colSpan: number
}) {
  const firstTradeId = agg.lots[0].trade_id ?? undefined
  const { expanded, setExpanded, chart } = useChartPanel(agg.symbol, firstTradeId, days)
  const pnlColor = agg.pnl >= 0 ? 'var(--green)' : 'var(--red)'
  const isMultiLot = agg.lots.length > 1
  const canSell = agg.lots.some(l => l.trade_id != null)

  return (
    <>
      <tr>
        <td style={{ padding: '12px 16px', fontWeight: 700, whiteSpace: 'nowrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {agg.symbol}
            {isMultiLot && (
              <span style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 4,
                background: 'var(--faint)', color: 'var(--muted)', fontWeight: 600,
              }}>
                {agg.lots.length} lots
              </span>
            )}
          </div>
        </td>
        <td style={{ padding: '12px 16px', whiteSpace: 'nowrap' }}>
          <span style={{
            fontSize: 11, padding: '2px 6px', borderRadius: 4,
            background: 'var(--faint)', color: 'var(--muted)', textTransform: 'uppercase',
          }}>{agg.mode}</span>
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--muted)', whiteSpace: 'nowrap' }}>{agg.qty}</td>
        <td style={{ padding: '12px 16px', whiteSpace: 'nowrap' }}>
          ₹{agg.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
        </td>
        <td style={{ padding: '12px 16px', fontWeight: 600, whiteSpace: 'nowrap' }}>
          ₹{agg.current_price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--red)', whiteSpace: 'nowrap' }}>
          {agg.stop_loss != null
            ? `₹${agg.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
            : '—'}
          {isMultiLot && agg.stop_loss != null && (
            <span title="Tightest SL across lots"
                  style={{ fontSize: 10, color: 'var(--dim)', marginLeft: 4 }}>
              (tightest)
            </span>
          )}
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
          {agg.sl_distance_pct != null ? `${agg.sl_distance_pct.toFixed(1)}%` : '—'}
        </td>
        <td style={{ padding: '12px 16px', color: pnlColor, fontWeight: 600, whiteSpace: 'nowrap' }}>
          {agg.pnl >= 0 ? '+' : ''}₹{agg.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </td>
        <td style={{ padding: '12px 16px', color: pnlColor, fontSize: 12, whiteSpace: 'nowrap' }}>
          {agg.pnl_pct >= 0 ? '+' : ''}{agg.pnl_pct.toFixed(1)}%
        </td>
        <td style={{ padding: '12px 16px', whiteSpace: 'nowrap' }}>
          {canSell ? (
            <HoverButton
              onClick={onSell}
              title={isMultiLot ? `Sell across ${agg.lots.length} lots (FIFO)` : 'Sell shares'}
              style={SELL_BUTTON_BASE}
              hoverStyle={SELL_BUTTON_HOVER}
              activeStyle={SELL_BUTTON_ACTIVE}
            >Sell</HoverButton>
          ) : (
            <span style={{ fontSize: 11, color: 'var(--dim)' }}>—</span>
          )}
        </td>
      </tr>
      {/* Bottom chevron row — full-width click target, subtle by default so it
       * doesn't compete with the Sell button but is easy to find on any row. */}
      <tr style={{ borderBottom: '1px solid var(--faint)' }}>
        <td colSpan={colSpan} style={{ padding: 0 }}>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              width: '100%', padding: '6px 0',
              background: expanded ? 'var(--faint)' : 'transparent',
              border: 'none',
              color: 'var(--muted)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              lineHeight: 0,
            }}
            title={expanded ? 'Hide details' : `Show ${isMultiLot ? `${agg.lots.length} lots` : 'purchase history'} + chart`}
            aria-label={expanded ? 'Hide details' : 'Show details'}
          >
            <svg
              width="10" height="6" viewBox="0 0 20 12"
              fill="none" stroke="currentColor"
              strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 150ms ease' }}
            >
              <polyline points="2 3 10 10 18 3" />
            </svg>
          </button>
        </td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: '1px solid var(--faint)' }}>
          <td colSpan={colSpan} style={{ padding: 0 }}>
            <div style={{ borderTop: '1px solid var(--border)' }}>
              <div style={{ padding: '12px 16px', background: 'var(--bg)' }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.05em' }}>
                  {isMultiLot ? `LOTS (${agg.lots.length})` : 'PURCHASE HISTORY'}
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', minWidth: 560 }}>
                    <thead>
                      <tr style={{ color: 'var(--dim)', fontSize: 10 }}>
                        {['#', 'Opened', 'Qty', 'Avg Cost', 'SL', 'Lot P&L', 'Lot P&L %'].map(h => (
                          <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 500 }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {agg.lots.map((lot, i) => {
                        const lotPnlColor = lot.pnl >= 0 ? 'var(--green)' : 'var(--red)'
                        return (
                          <tr key={lot.trade_id ?? i} style={{ borderTop: '1px solid var(--faint)' }}>
                            <td style={{ padding: '8px 10px', color: 'var(--dim)' }}>{i + 1}</td>
                            <td style={{ padding: '8px 10px', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                              {lot.opened_at != null
                                ? new Date(lot.opened_at).toLocaleDateString('en-IN', {
                                    day: 'numeric', month: 'short', year: 'numeric',
                                  })
                                : '—'}
                            </td>
                            <td style={{ padding: '8px 10px' }}>{lot.qty}</td>
                            <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                              ₹{lot.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            </td>
                            <td style={{ padding: '8px 10px', color: 'var(--red)', whiteSpace: 'nowrap' }}>
                              {lot.stop_loss != null
                                ? `₹${lot.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
                                : '—'}
                            </td>
                            <td style={{ padding: '8px 10px', color: lotPnlColor, fontWeight: 600, whiteSpace: 'nowrap' }}>
                              {lot.pnl >= 0 ? '+' : ''}₹{lot.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                            </td>
                            <td style={{ padding: '8px 10px', color: lotPnlColor }}>
                              {lot.pnl_pct >= 0 ? '+' : ''}{lot.pnl_pct.toFixed(1)}%
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
              <ChartPanelBody chart={chart} indicators={indicators} height={320} />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Positions() {
  const snap   = usePortfolioSnapshot()
  const trades = useSwingPositions()
  const error  = snap.error || trades.error

  const daily = useDailyHoldingsSummary()
  const refreshDaily = useRefreshAiSummary('daily')

  const [sellTarget, setSellTarget] = useState<AggregatedPosition | null>(null)
  const [days, setDays] = useState(90)
  const [indicators, setIndicators] = useState<ChartIndicators>(DEFAULT_CHART_INDICATORS)
  const toggleInd = (k: keyof ChartIndicators) =>
    setIndicators(prev => ({ ...prev, [k]: !prev[k] }))

  const positions = snap.data?.positions ?? []
  const aggregated = useMemo(() => aggregate(positions), [positions])

  if (error) return <ErrorBanner message={String(error)} />

  const HEADERS = ['Symbol', 'Mode', 'Qty', 'Avg Cost', 'CMP', 'Stop Loss', 'SL Dist', 'P&L', 'P&L %', '']

  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1, minWidth: 0, maxWidth: 1000 }}>

      {snap.data && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            {aggregated.length} position{aggregated.length !== 1 ? 's' : ''}
            {positions.length !== aggregated.length && (
              <span style={{ color: 'var(--dim)' }}>
                {' '}({positions.length} lots collapsed)
              </span>
            )}
          </span>
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

      {!snap.isLoading && aggregated.length > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center',
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '10px 14px',
        }}>
          <DaysControl days={days} setDays={setDays} />
          <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
          <OverlayControls indicators={indicators} toggleIndicator={toggleInd} />
        </div>
      )}

      {snap.isLoading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[...Array(3)].map((_, i) => <Skeleton key={i} h={60} />)}
        </div>
      ) : (
        // overflow-x: auto lets narrow viewports scroll the wide table instead
        // of clipping columns off the right edge.
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 12, overflowX: 'auto',
        }}>
          <table style={{ width: '100%', minWidth: 900, fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: 'var(--muted)', fontSize: 11, borderBottom: '1px solid var(--border)' }}>
                {HEADERS.map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {aggregated.map(agg => (
                <AggregatedRow
                  key={`${agg.symbol}|${agg.mode}`}
                  agg={agg}
                  days={days}
                  indicators={indicators}
                  onSell={() => setSellTarget(agg)}
                  colSpan={HEADERS.length}
                />
              ))}
              {!aggregated.length && (
                <tr>
                  <td colSpan={HEADERS.length} style={{ padding: '32px 16px', textAlign: 'center', fontSize: 13, color: 'var(--dim)' }}>
                    No open positions
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      </div>

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

      {sellTarget && (
        <SellModal
          agg={sellTarget}
          onClose={() => setSellTarget(null)}
        />
      )}
    </div>
  )
}
