const PILLAR_MAX: Record<string, number> = {
  Technical: 30, Expectancy: 25, Flow: 15,
  Sentiment: 5, 'Regime fit': 15, Fundamentals: 10,
}

export function PillarBar({ label, value }: { label: string; value: number }) {
  const max = PILLAR_MAX[label] ?? 100
  const pct = Math.min(100, (value / max) * 100)
  const color = pct >= 70 ? 'var(--green)' : pct >= 40 ? 'var(--amber)' : 'var(--red)'

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between text-xs" style={{ color: 'var(--muted)' }}>
        <span>{label}</span>
        <span style={{ color }}>{value}/{max}</span>
      </div>
      <div style={{ background: 'var(--faint)', borderRadius: 3, height: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, background: color, height: '100%', borderRadius: 3 }} />
      </div>
    </div>
  )
}
