import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { apiClient } from '../api/client'

export default function Login() {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const setStoreToken = useAuthStore(s => s.setToken)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await apiClient.post('/auth/verify', null, {
        headers: { Authorization: `Bearer ${token.trim()}` },
      })
      setStoreToken(token.trim())
      navigate('/', { replace: true })
    } catch {
      setError('Invalid token')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center"
         style={{ background: 'var(--bg)' }}>
      <form onSubmit={handleSubmit}
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
            className="rounded-xl p-8 w-full max-w-sm flex flex-col gap-4">
        <div className="flex items-center gap-2 mb-2">
          <span style={{ color: 'var(--green)' }} className="text-xl font-bold">▲</span>
          <h1 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>Plutus</h1>
        </div>
        <label className="text-sm" style={{ color: 'var(--muted)' }}>Access token</label>
        <input
          type="password"
          value={token}
          onChange={e => setToken(e.target.value)}
          placeholder="Enter token"
          autoFocus
          style={{
            background: 'var(--bg)',
            border: `1px solid ${error ? 'var(--red)' : 'var(--border)'}`,
            color: 'var(--text)',
          }}
          className="rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 ring-blue-500"
        />
        {error && <p className="text-sm" style={{ color: 'var(--red)' }}>{error}</p>}
        <button
          type="submit"
          disabled={!token || loading}
          style={{ background: 'var(--green)', color: '#000' }}
          className="rounded-lg py-2 text-sm font-semibold disabled:opacity-40">
          {loading ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </div>
  )
}
