export function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{ background: 'var(--red-bg)', border: '1px solid var(--red)', color: 'var(--red)' }}
         className="rounded-lg px-4 py-3 text-sm">
      {message}
    </div>
  )
}
