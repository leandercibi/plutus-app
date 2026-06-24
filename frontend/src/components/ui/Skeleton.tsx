export function Skeleton({ w = '100%', h = 20 }: { w?: string | number; h?: number }) {
  return (
    <div
      style={{
        width: w,
        height: h,
        background: 'var(--faint)',
        borderRadius: 4,
        animation: 'pulse 1.4s ease-in-out infinite',
      }}
    />
  )
}
