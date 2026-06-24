interface StatCardProps {
  label: string
  value: string | number
  sub?: string
  trend?: 'up' | 'down' | 'neutral'
}

export function StatCard({ label, value, sub, trend }: StatCardProps) {
  const trendColor = trend === 'up' ? 'var(--green)' : trend === 'down' ? 'var(--red)' : 'var(--muted)'

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
         className="rounded-xl p-4 flex flex-col gap-1">
      <span className="text-xs" style={{ color: 'var(--muted)' }}>{label}</span>
      <span className="text-xl font-semibold" style={{ color: trendColor }}>{value}</span>
      {sub && <span className="text-xs" style={{ color: 'var(--dim)' }}>{sub}</span>}
    </div>
  )
}
