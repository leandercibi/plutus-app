import { useEffect, useRef } from 'react'
import {
  createChart, ColorType, LineStyle,
  CandlestickSeries, LineSeries, HistogramSeries,
  createSeriesMarkers,
} from 'lightweight-charts'
import type { ChartResponse } from '../../types/api'

interface Props {
  data: ChartResponse
  height?: number
  showMACD?: boolean
  showBB?: boolean
  showGoldenCross?: boolean
}

const COLORS = {
  bg:      '#0F1119',
  grid:    '#1C2030',
  text:    '#7A8499',
  up:      '#00C896',
  down:    '#F23645',
  dma20:   '#4B8EF5',
  dma50:   '#F59E0B',
  dma200:  '#E05C6B',
  bb:      'rgba(120,160,255,0.6)',
  macd:    '#4B8EF5',
  signal:  '#F59E0B',
  histPos: '#00C896',
  histNeg: '#F23645',
  gx:      '#F59E0B',
}

function LegendDot({ color }: { color: string }) {
  return (
    <span style={{
      display: 'inline-block', width: 22, height: 2,
      background: color, borderRadius: 1, verticalAlign: 'middle',
    }} />
  )
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <LegendDot color={color} />
      <span style={{ fontSize: 10, color: COLORS.text, whiteSpace: 'nowrap' }}>{label}</span>
    </div>
  )
}

export function StockChart({
  data,
  height = 300,
  showMACD = false,
  showBB = false,
  showGoldenCross = false,
}: Props) {
  const mainRef = useRef<HTMLDivElement>(null)
  const macdRef = useRef<HTMLDivElement>(null)

  const MAIN_H = showMACD ? Math.floor(height * 0.62) : height
  const MACD_H = showMACD ? height - MAIN_H : 0

  useEffect(() => {
    if (!mainRef.current || !data.bars.length) return

    type TV_Time = import('lightweight-charts').Time
    const toTime = (d: string) => d as unknown as TV_Time

    // ── Main chart ─────────────────────────────────────────────
    const chart = createChart(mainRef.current, {
      width: mainRef.current.clientWidth,
      height: MAIN_H,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.bg },
        textColor: COLORS.text,
      },
      grid: {
        vertLines: { color: COLORS.grid },
        horzLines: { color: COLORS.grid },
      },
      timeScale: { borderColor: COLORS.grid },
      rightPriceScale: { borderColor: COLORS.grid },
      crosshair: { mode: 1 },
    })

    // Candlesticks
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.up, downColor: COLORS.down,
      borderUpColor: COLORS.up, borderDownColor: COLORS.down,
      wickUpColor: COLORS.up, wickDownColor: COLORS.down,
    })
    candles.setData(data.bars.map(b => ({
      time: toTime(b.date), open: b.open, high: b.high, low: b.low, close: b.close,
    })))

    // DMA helpers
    const addLine = (
      vals: (number | undefined)[],
      color: string,
      lw: 1 | 2 | 3 | 4,
      style?: number,
    ) => {
      const pts = data.bars
        .map((b, i) => ({ t: b.date, v: vals[i] }))
        .filter((p): p is { t: string; v: number } => p.v != null)
      if (!pts.length) return
      const s = chart.addSeries(LineSeries, {
        color, lineWidth: lw,
        lineStyle: style ?? LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      s.setData(pts.map(p => ({ time: toTime(p.t), value: p.v })))
    }

    addLine(data.bars.map(b => b.dma20),  COLORS.dma20,  1)
    addLine(data.bars.map(b => b.dma50),  COLORS.dma50,  1)
    addLine(data.bars.map(b => b.dma200), COLORS.dma200, 1, LineStyle.Dashed)

    // Bollinger Bands
    if (showBB) {
      addLine(data.bars.map(b => b.bb_upper), COLORS.bb, 1)
      addLine(data.bars.map(b => b.bb_mid),   COLORS.bb, 1, LineStyle.Dotted)
      addLine(data.bars.map(b => b.bb_lower), COLORS.bb, 1)
    }

    // Signal price levels
    const m = data.signal_marker
    if (m) {
      const addLevel = (price: number | undefined, color: string, title: string) => {
        if (!price) return
        candles.createPriceLine({ price, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title })
      }
      addLevel(m.entry,     COLORS.up,   'Entry')
      addLevel(m.stop_loss, COLORS.down, 'SL')
      addLevel(m.target_1,  COLORS.dma20,'T1')
      addLevel(m.target_2,  COLORS.dma20,'T2')
    }

    // Golden Cross markers
    if (showGoldenCross) {
      const crosses = data.bars.filter(b => b.golden_cross_20_50)
      if (crosses.length) {
        createSeriesMarkers(candles, crosses.map(b => ({
          time: toTime(b.date),
          position: 'aboveBar' as const,
          color: COLORS.gx,
          shape: 'circle' as const,
          text: '✕',
          size: 0.6,
        })))
      }
    }

    chart.timeScale().fitContent()

    // ── MACD chart ─────────────────────────────────────────────
    let macdChart: ReturnType<typeof createChart> | null = null
    if (showMACD && macdRef.current && MACD_H > 0) {
      macdChart = createChart(macdRef.current, {
        width: macdRef.current.clientWidth,
        height: MACD_H,
        layout: { background: { type: ColorType.Solid, color: COLORS.bg }, textColor: COLORS.text },
        grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
        timeScale: { borderColor: COLORS.grid, visible: true },
        rightPriceScale: { borderColor: COLORS.grid },
        crosshair: { mode: 1 },
      })

      const histSeries = macdChart.addSeries(HistogramSeries, {
        priceLineVisible: false, lastValueVisible: false,
      })
      histSeries.setData(
        data.bars
          .map(b => ({ t: b.date, v: b.macd_hist }))
          .filter((p): p is { t: string; v: number } => p.v != null)
          .map(p => ({ time: toTime(p.t), value: p.v, color: p.v >= 0 ? COLORS.histPos : COLORS.histNeg }))
      )

      const macdLine = macdChart.addSeries(LineSeries, {
        color: COLORS.macd, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      })
      macdLine.setData(
        data.bars
          .filter(b => b.macd != null)
          .map(b => ({ time: toTime(b.date), value: b.macd! }))
      )

      const sigLine = macdChart.addSeries(LineSeries, {
        color: COLORS.signal, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      })
      sigLine.setData(
        data.bars
          .filter(b => b.macd_signal != null)
          .map(b => ({ time: toTime(b.date), value: b.macd_signal! }))
      )

      macdChart.timeScale().fitContent()
    }

    const ro = new ResizeObserver(() => {
      const w = mainRef.current?.clientWidth ?? 0
      chart.applyOptions({ width: w })
      if (macdRef.current) macdChart?.applyOptions({ width: macdRef.current.clientWidth })
    })
    if (mainRef.current) ro.observe(mainRef.current)

    return () => {
      chart.remove()
      macdChart?.remove()
      ro.disconnect()
    }
  }, [data, MAIN_H, MACD_H, showMACD, showBB, showGoldenCross])

  return (
    <div style={{ width: '100%' }}>
      {/* Main chart + legend */}
      <div style={{ position: 'relative', width: '100%' }}>
        <div ref={mainRef} style={{ width: '100%' }} />

        {/* Legend overlay */}
        <div style={{
          position: 'absolute', top: 8, left: 8, zIndex: 10,
          background: 'rgba(15,17,25,0.82)',
          border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 6, padding: '5px 9px',
          display: 'flex', flexDirection: 'column', gap: 4,
          backdropFilter: 'blur(4px)',
        }}>
          <LegendItem color={COLORS.dma20}  label="DMA 20" />
          <LegendItem color={COLORS.dma50}  label="DMA 50" />
          <LegendItem color={COLORS.dma200} label="DMA 200 ---" />
          {showBB && <LegendItem color={COLORS.bb} label="BB Bands" />}
          {showGoldenCross && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 12, color: COLORS.gx }}>✕</span>
              <span style={{ fontSize: 10, color: COLORS.text }}>Golden Cross</span>
            </div>
          )}
        </div>
      </div>

      {/* MACD pane */}
      {showMACD && (
        <div style={{ width: '100%' }}>
          <div style={{
            display: 'flex', gap: 12, alignItems: 'center',
            padding: '4px 8px',
            borderTop: `1px solid ${COLORS.grid}`,
            background: COLORS.bg,
          }}>
            <span style={{ fontSize: 10, color: COLORS.text, fontWeight: 600, letterSpacing: '0.05em' }}>MACD</span>
            <LegendItem color={COLORS.macd}   label="MACD" />
            <LegendItem color={COLORS.signal} label="Signal" />
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ display: 'inline-block', width: 10, height: 10, background: COLORS.histPos, borderRadius: 2 }} />
              <span style={{ fontSize: 10, color: COLORS.text }}>Hist</span>
            </div>
          </div>
          <div ref={macdRef} style={{ width: '100%' }} />
        </div>
      )}
    </div>
  )
}
