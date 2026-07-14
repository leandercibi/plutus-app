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
  useChartPanel, ChartToggleButton, ChartPanelBody, DaysControl, OverlayControls,
  DEFAULT_CHART_INDICATORS, type ChartIndicators,
} from '../components/chart/ChartPanel'
import type { PositionSnapshot } from '../types/api'

// ── Hover-aware button ────────────────────────────────────────────────────────

/** Tiny wrapper that gives inline-styled buttons a visible hover + pressed state.
 * The codebase uses inline styles throughout, and inline styles can't express
 * :hover / :active, so we track hover/press in state and apply the caller's
 * `hoverStyle` / `activeStyle` overrides on top of the base. Keeps every action
 * button on this page consistent without pulling in a CSS solution. */
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

/** One row-per-symbol view built from the raw per-lot PositionSnapshot rows
 * the backend returns. Weighted avg cost, weighted P&L%, tightest (i.e. first
 * to trigger) stop-loss — matches how brokers display consolidated positions.
 * The original per-lot rows are preserved as `lots` for the expandable view
 * and for dispatching per-lot Exit / partial-sell actions to the right trade. */
type AggregatedPosition = {
  symbol: string
  mode: string
  qty: number
  avg_cost: number             // weighted by lot qty
  current_price: number
  invested: number
  pnl: number                  // sum of lot pnls (₹)
  pnl_pct: number              // weighted by invested, not average-of-percents
  stop_loss: number | null     // tightest SL across lots
  sl_distance_pct: number | null
  lots: PositionSnapshot[]
}

function aggregate(positions: PositionSnapshot[]): AggregatedPosition[] {
  // Group by symbol+mode so a hypothetical swing + accumulation on the same
  // symbol stay distinct (they display differently and have different actions).
  const groups = new Map<string, PositionSnapshot[]>()
  for (const p of positions) {
    const key = `${p.symbol}|${p.mode}`
    const existing = groups.get(key)
    if (existing) existing.push(p)
    else groups.set(key, [p])
  }

  const out: AggregatedPosition[] = []
  for (const lots of groups.values()) {
    const qty = lots.reduce((s, l) => s + l.qty, 0)
    const invested = lots.reduce((s, l) => s + l.avg_cost * l.qty, 0)
    const current_price = lots[0].current_price   // all lots for a symbol share the same CMP
    const pnl = lots.reduce((s, l) => s + l.pnl, 0)
    const avg_cost = qty > 0 ? invested / qty : 0
    const pnl_pct = invested > 0 ? (pnl / invested) * 100 : 0

    // Tightest = highest SL (for long positions the SL sits below entry, so the
    // highest number is closest to CMP → triggers first → the risk to know about).
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
  // Biggest movers first — winners AND losers surface, since |pnl| is what you
  // scan for when deciding "what needs my attention right now".
  out.sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))
  return out
}

// ── Sell modal (full close or partial sell) ───────────────────────────────────

const EXIT_REASONS = [
  'Target reached',
  'Stop loss hit',
  'Trailing stop hit',
  'Thesis invalidated',
  'Portfolio rebalance',
  'Manual exit',
]

function SellModal({
  lot,
  onClose,
}: {
  lot: PositionSnapshot   // must have trade_id for a sell to be possible
  onClose: () => void
}) {
  const ltpQuery  = useLTP(lot.symbol)
  const cmp       = ltpQuery.data ?? lot.current_price
  const exitTrade = useExitTrade()

  const [qty, setQty]       = useState(String(lot.qty))
  const [reason, setReason] = useState(EXIT_REASONS[0])
  const [customReason, setCustomReason] = useState('')

  const qtyVal = parseInt(qty, 10)
  const isValid = !isNaN(qtyVal) && qtyVal > 0 && qtyVal <= lot.qty
  const isPartial = isValid && qtyVal < lot.qty

  const exitPrice = cmp
  const totalValue = isValid && exitPrice ? qtyVal * exitPrice : null
  const pnl = totalValue != null ? totalValue - qtyVal * lot.avg_cost : null

  const finalReason = reason === 'Manual exit' && customReason.trim()
    ? customReason.trim()
    : reason

  const handleSubmit = () => {
    if (!isValid || lot.trade_id == null) return
    exitTrade.mutate(
      // Omit qty on full close so backend hits the classic close-and-set-state
      // path. Send it on partial so backend logs a SELL fill and stays OPEN.
      { tradeId: lot.trade_id, reason: finalReason, qty: isPartial ? qtyVal : undefined },
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
        borderRadius: 16, padding: 28, width: 460, maxWidth: '92vw',
        display: 'flex', flexDirection: 'column', gap: 20,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18 }}>{lot.symbol}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3 }}>
              {isPartial ? 'Partial sell' : 'Full exit'} · {lot.qty} shares in this lot
              {lot.opened_at != null && (
                <span style={{ color: 'var(--dim)' }}>
                  {' · opened '}
                  {new Date(lot.opened_at).toLocaleDateString('en-IN', {
                    day: 'numeric', month: 'short', year: 'numeric',
                  })}
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--muted)',
            fontSize: 18, cursor: 'pointer', padding: '0 4px', lineHeight: 1,
          }}>✕</button>
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
          background: 'var(--faint)', borderRadius: 10, padding: '12px 14px',
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>AVG COST</div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>
              ₹{lot.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>CMP</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--blue)' }}>
              {ltpQuery.isLoading ? '…' : `₹${cmp.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`}
            </div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 3 }}>LOT P&L</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: lot.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {lot.pnl >= 0 ? '+' : ''}₹{lot.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
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
              max={lot.qty}
              style={{
                flex: 1, padding: '9px 12px', fontSize: 14,
                background: 'var(--bg)',
                border: `1px solid ${isValid || !qty ? 'var(--border)' : 'var(--red)'}`,
                borderRadius: 8, color: 'var(--text)', outline: 'none', boxSizing: 'border-box',
              }}
            />
            <HoverButton
              onClick={() => setQty(String(lot.qty))}
              // Highlight when "all" is currently selected so it's obvious the click
              // actually did something — otherwise the click just silently updates
              // the qty input, which users routinely miss.
              style={{
                padding: '9px 14px', fontSize: 12, fontWeight: 600,
                whiteSpace: 'nowrap', borderRadius: 8,
                border: qtyVal === lot.qty ? '1px solid var(--green)' : '1px solid var(--border)',
                background: qtyVal === lot.qty ? 'rgba(0,200,150,0.18)' : 'var(--faint)',
                color: qtyVal === lot.qty ? 'var(--green)' : 'var(--muted)',
              }}
              hoverStyle={qtyVal === lot.qty
                ? { background: 'rgba(0,200,150,0.28)' }
                : { background: 'var(--border)' }}
              activeStyle={{ filter: 'brightness(0.92)' }}
            >
              {qtyVal === lot.qty ? `✓ All ${lot.qty}` : `All ${lot.qty}`}
            </HoverButton>
          </div>
          {isValid && (
            <input
              type="range"
              min={1}
              max={lot.qty}
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
                  REALISED P&L (on {qtyVal} shares)
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                </div>
              </div>
            )}
            {isPartial && (
              <div style={{ gridColumn: '1/-1', fontSize: 11, color: 'var(--amber)' }}>
                Partial: {lot.qty - qtyVal} shares will remain in this lot.
              </div>
            )}
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

        {exitTrade.isError && (
          <div style={{ fontSize: 12, color: 'var(--red)', background: 'rgba(242,54,69,0.08)', padding: '8px 12px', borderRadius: 8 }}>
            {String(exitTrade.error)}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose} style={{
            flex: 1, padding: '10px 0',
            background: 'transparent', border: '1px solid var(--border)',
            borderRadius: 10, color: 'var(--muted)', fontSize: 13, cursor: 'pointer',
          }}>Cancel</button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || exitTrade.isPending || lot.trade_id == null}
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
              ? (isPartial ? 'Selling…' : 'Closing…')
              : `${isPartial ? 'Sell' : 'Exit'} ${qtyVal || '—'} shares · ₹${totalValue?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Exit-All confirm dialog ────────────────────────────────────────────────────

function ExitAllModal({
  agg,
  onClose,
}: {
  agg: AggregatedPosition
  onClose: () => void
}) {
  const exitTrade = useExitTrade()
  const sellableLots = agg.lots.filter(l => l.trade_id != null)
  const isPending = exitTrade.isPending

  const handleConfirm = async () => {
    // Fire sequentially, not Promise.all: each mutation invalidates the
    // portfolio-snapshot query on success; parallel calls risk racing with
    // stale trade.qty reads on the backend. Sequential is slower but correct.
    for (const lot of sellableLots) {
      const tradeId = lot.trade_id
      if (tradeId == null) continue
      await new Promise<void>((resolve, reject) => {
        exitTrade.mutate(
          { tradeId, reason: 'Exit all lots' },
          { onSuccess: () => resolve(), onError: err => reject(err) },
        )
      })
    }
    onClose()
  }

  const handleBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && !isPending) onClose()
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
        display: 'flex', flexDirection: 'column', gap: 18,
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: 18 }}>Exit all {agg.symbol}?</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            Closes {sellableLots.length} lot{sellableLots.length !== 1 ? 's' : ''}
            {' · '}{agg.qty} shares total{' · '}
            <span style={{ color: agg.pnl >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 700 }}>
              {agg.pnl >= 0 ? '+' : ''}₹{agg.pnl.toLocaleString('en-IN')} realised
            </span>
          </div>
        </div>

        <div style={{
          fontSize: 12, color: 'var(--amber)',
          background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.35)',
          borderRadius: 8, padding: '10px 12px',
        }}>
          Each lot has its own entry price and tax bucket — closing them together
          realises capital gains across all of them at once. Prefer per-lot exit
          if you're managing tax lots.
        </div>

        {exitTrade.isError && (
          <div style={{ fontSize: 12, color: 'var(--red)', background: 'rgba(242,54,69,0.08)', padding: '8px 12px', borderRadius: 8 }}>
            One or more lots failed to close: {String(exitTrade.error)}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose} disabled={isPending} style={{
            flex: 1, padding: '10px 0',
            background: 'transparent', border: '1px solid var(--border)',
            borderRadius: 10, color: 'var(--muted)', fontSize: 13, cursor: isPending ? 'default' : 'pointer',
          }}>Cancel</button>
          <button
            onClick={handleConfirm}
            disabled={isPending || sellableLots.length === 0}
            style={{
              flex: 2, padding: '10px 0',
              background: 'var(--red)', border: 'none', borderRadius: 10,
              color: '#fff', fontSize: 13, fontWeight: 700,
              cursor: isPending ? 'default' : 'pointer',
              opacity: isPending ? 0.6 : 1,
            }}
          >
            {isPending ? 'Closing all…' : `Exit all ${agg.qty} shares`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Aggregated row (with expandable chart + per-lot detail) ────────────────────

function AggregatedRow({
  agg,
  days,
  indicators,
  onSellLot,
  onExitAll,
}: {
  agg: AggregatedPosition
  days: number
  indicators: ChartIndicators
  onSellLot: (lot: PositionSnapshot) => void
  onExitAll: () => void
}) {
  // Use the first lot's trade for signal-based chart markers (Entry/SL/T1/T2).
  // Different lots for the same symbol may have different signal_ids, but the
  // aggregated view can only show one set of markers — first lot is a reasonable
  // default; per-lot lines would be visually noisy.
  const firstTradeId = agg.lots[0].trade_id ?? undefined
  const { expanded, setExpanded, chart } = useChartPanel(agg.symbol, firstTradeId, days)
  const pnlColor = agg.pnl >= 0 ? 'var(--green)' : 'var(--red)'
  const isMultiLot = agg.lots.length > 1
  const sellableLots = agg.lots.filter(l => l.trade_id != null)
  const canExit = sellableLots.length > 0

  return (
    <>
      <tr style={{ borderBottom: expanded ? 'none' : '1px solid var(--faint)' }}>
        <td style={{ padding: '12px 16px', fontWeight: 700 }}>
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
        <td style={{ padding: '12px 16px' }}>
          <span style={{
            fontSize: 11, padding: '2px 6px', borderRadius: 4,
            background: 'var(--faint)', color: 'var(--muted)', textTransform: 'uppercase',
          }}>{agg.mode}</span>
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--muted)' }}>{agg.qty}</td>
        <td style={{ padding: '12px 16px' }}>
          ₹{agg.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
        </td>
        <td style={{ padding: '12px 16px', fontWeight: 600 }}>
          ₹{agg.current_price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--red)' }}>
          {agg.stop_loss != null
            ? `₹${agg.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
            : '—'}
          {isMultiLot && agg.stop_loss != null && (
            <span title="Tightest SL across lots — expand to see all"
                  style={{ fontSize: 10, color: 'var(--dim)', marginLeft: 4 }}>
              (tightest)
            </span>
          )}
        </td>
        <td style={{ padding: '12px 16px', color: 'var(--muted)', fontSize: 12 }}>
          {agg.sl_distance_pct != null ? `${agg.sl_distance_pct.toFixed(1)}%` : '—'}
        </td>
        <td style={{ padding: '12px 16px', color: pnlColor, fontWeight: 600 }}>
          {agg.pnl >= 0 ? '+' : ''}₹{agg.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </td>
        <td style={{ padding: '12px 16px', color: pnlColor, fontSize: 12 }}>
          {agg.pnl_pct >= 0 ? '+' : ''}{agg.pnl_pct.toFixed(1)}%
        </td>
        <td style={{ padding: '12px 16px' }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {canExit ? (
              isMultiLot ? (
                <HoverButton
                  onClick={onExitAll}
                  title="Close every lot for this symbol"
                  style={{ ...SELL_BUTTON_BASE, padding: '5px 10px' }}
                  hoverStyle={SELL_BUTTON_HOVER}
                  activeStyle={SELL_BUTTON_ACTIVE}
                >Exit all</HoverButton>
              ) : (
                <HoverButton
                  onClick={() => onSellLot(agg.lots[0])}
                  style={SELL_BUTTON_BASE}
                  hoverStyle={SELL_BUTTON_HOVER}
                  activeStyle={SELL_BUTTON_ACTIVE}
                >Sell</HoverButton>
              )
            ) : (
              <span style={{ fontSize: 11, color: 'var(--dim)' }}>—</span>
            )}
            <ChartToggleButton
              expanded={expanded}
              onToggle={() => setExpanded(e => !e)}
              label={isMultiLot ? 'Lots' : 'History'}
            />
          </div>
        </td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: '1px solid var(--faint)' }}>
          <td colSpan={10} style={{ padding: 0 }}>
            <div style={{ borderTop: '1px solid var(--border)' }}>
              {agg.lots.length > 0 && (
                <div style={{ padding: '12px 16px', background: 'var(--bg)' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8, letterSpacing: '0.05em' }}>
                    {isMultiLot ? `LOTS (${agg.lots.length})` : 'PURCHASE HISTORY'}
                  </div>
                  <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ color: 'var(--dim)', fontSize: 10 }}>
                        {['Opened', 'Qty', 'Avg Cost', 'SL', 'Lot P&L', 'Lot P&L %', ''].map(h => (
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
                            <td style={{ padding: '8px 10px', color: 'var(--muted)' }}>
                              {lot.opened_at != null
                                ? new Date(lot.opened_at).toLocaleDateString('en-IN', {
                                    day: 'numeric', month: 'short', year: 'numeric',
                                  })
                                : '—'}
                            </td>
                            <td style={{ padding: '8px 10px' }}>{lot.qty}</td>
                            <td style={{ padding: '8px 10px' }}>
                              ₹{lot.avg_cost.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            </td>
                            <td style={{ padding: '8px 10px', color: 'var(--red)' }}>
                              {lot.stop_loss != null
                                ? `₹${lot.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
                                : '—'}
                            </td>
                            <td style={{ padding: '8px 10px', color: lotPnlColor, fontWeight: 600 }}>
                              {lot.pnl >= 0 ? '+' : ''}₹{lot.pnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                            </td>
                            <td style={{ padding: '8px 10px', color: lotPnlColor }}>
                              {lot.pnl_pct >= 0 ? '+' : ''}{lot.pnl_pct.toFixed(1)}%
                            </td>
                            <td style={{ padding: '8px 10px' }}>
                              {lot.trade_id != null ? (
                                <HoverButton
                                  onClick={() => onSellLot(lot)}
                                  style={{ ...SELL_BUTTON_BASE, padding: '3px 10px' }}
                                  hoverStyle={SELL_BUTTON_HOVER}
                                  activeStyle={SELL_BUTTON_ACTIVE}
                                >Sell</HoverButton>
                              ) : (
                                <span style={{ fontSize: 11, color: 'var(--dim)' }}>—</span>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
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
  const trades = useSwingPositions()   // still used indirectly via trade_id on lots
  const error  = snap.error || trades.error

  const daily = useDailyHoldingsSummary()
  const refreshDaily = useRefreshAiSummary('daily')

  const [sellLot, setSellLot] = useState<PositionSnapshot | null>(null)
  const [exitAllTarget, setExitAllTarget] = useState<AggregatedPosition | null>(null)
  const [days, setDays] = useState(90)
  const [indicators, setIndicators] = useState<ChartIndicators>(DEFAULT_CHART_INDICATORS)
  const toggleInd = (k: keyof ChartIndicators) =>
    setIndicators(prev => ({ ...prev, [k]: !prev[k] }))

  const positions = snap.data?.positions ?? []
  const aggregated = useMemo(() => aggregate(positions), [positions])

  if (error) return <ErrorBanner message={String(error)} />

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
              {aggregated.map(agg => (
                <AggregatedRow
                  key={`${agg.symbol}|${agg.mode}`}
                  agg={agg}
                  days={days}
                  indicators={indicators}
                  onSellLot={setSellLot}
                  onExitAll={() => setExitAllTarget(agg)}
                />
              ))}
              {!aggregated.length && (
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

      {sellLot && (
        <SellModal
          lot={sellLot}
          onClose={() => setSellLot(null)}
        />
      )}
      {exitAllTarget && (
        <ExitAllModal
          agg={exitAllTarget}
          onClose={() => setExitAllTarget(null)}
        />
      )}
    </div>
  )
}
