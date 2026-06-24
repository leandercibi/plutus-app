import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useTriggerSundayRun, useTriggerMondayRun, useTriggerMidweekRun } from '../../api/hooks'
import { ClockIcon, PlayIcon, ChevronDownIcon, RefreshIcon } from '../icons'

const PAGE_TITLES: Record<string, string> = {
  '/':             'Dashboard',
  '/signals':      'Signals',
  '/positions':    'Positions',
  '/candidates':   'Accumulation Candidates',
  '/accumulation': 'Accumulation Positions',
  '/strategy-lab': 'Strategy Lab',
  '/calibration':  'Calibration',
  '/postmortem':   'Weekly Postmortem',
  '/glossary':     'Glossary',
}

function ISTClock() {
  const [time, setTime] = useState('')
  useEffect(() => {
    const tick = () => {
      const t = new Date().toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit',
      })
      setTime(t + ' IST')
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--dim)', fontSize: 12 }}>
      <ClockIcon size={12} />
      <span style={{ fontFamily: 'monospace', letterSpacing: '0.02em' }}>{time}</span>
    </div>
  )
}

type RunStatus = 'idle' | 'loading' | 'ok' | 'error'

function TriggerButton() {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<RunStatus>('idle')
  const [lastRun, setLastRun] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const sunday = useTriggerSundayRun()
  const monday = useTriggerMondayRun()
  const midweek = useTriggerMidweekRun()

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const trigger = async (label: string, fn: () => Promise<unknown>) => {
    setOpen(false)
    setStatus('loading')
    setLastRun(label)
    try {
      await fn()
      setStatus('ok')
      setTimeout(() => setStatus('idle'), 4000)
    } catch {
      setStatus('error')
      setTimeout(() => setStatus('idle'), 4000)
    }
  }

  const RUNS = [
    { label: 'Sunday Full Run',      fn: () => sunday.mutateAsync(undefined) },
    { label: 'Monday Revalidation',  fn: () => monday.mutateAsync(undefined) },
    { label: 'Midweek Mini Run',     fn: () => midweek.mutateAsync(undefined) },
  ]

  const statusColor =
    status === 'loading' ? 'var(--amber)'
    : status === 'ok' ? 'var(--green)'
    : status === 'error' ? 'var(--red)'
    : 'var(--text)'

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        disabled={status === 'loading'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 12px',
          background: status === 'ok' ? 'var(--green-bg)'
            : status === 'error' ? 'var(--red-bg)'
            : 'rgba(75,142,245,0.1)',
          border: `1px solid ${statusColor === 'var(--text)' ? 'var(--blue)' : statusColor}`,
          borderRadius: 8,
          color: statusColor === 'var(--text)' ? 'var(--blue)' : statusColor,
          fontSize: 12,
          fontWeight: 600,
          cursor: status === 'loading' ? 'not-allowed' : 'pointer',
          opacity: status === 'loading' ? 0.7 : 1,
        }}>
        {status === 'loading' ? <RefreshIcon size={13} /> : <PlayIcon size={13} />}
        {status === 'loading' ? `Running ${lastRun}…`
          : status === 'ok' ? `${lastRun} started`
          : status === 'error' ? 'Run failed'
          : 'Trigger Run'}
        {status === 'idle' && <ChevronDownIcon size={12} />}
      </button>

      {open && (
        <div style={{
          position: 'absolute',
          top: 'calc(100% + 6px)',
          right: 0,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 10,
          overflow: 'hidden',
          minWidth: 200,
          zIndex: 50,
          boxShadow: '0 4px 24px rgba(0,0,0,0.4)',
        }}>
          {RUNS.map(({ label, fn }) => (
            <button
              key={label}
              onClick={() => trigger(label, fn)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                width: '100%',
                padding: '10px 14px',
                fontSize: 13,
                color: 'var(--text)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--faint)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
              <PlayIcon size={12} />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Topbar() {
  const { pathname } = useLocation()
  const title = PAGE_TITLES[pathname] ?? 'Plutus'

  return (
    <div style={{
      height: 52,
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
      flexShrink: 0,
      background: 'var(--bg)',
    }}>
      <h1 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{title}</h1>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <ISTClock />
        <TriggerButton />
      </div>
    </div>
  )
}
