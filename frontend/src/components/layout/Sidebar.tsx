import { NavLink } from 'react-router-dom'
import { useAuthStore } from '../../store/auth'
import {
  DashboardIcon, SignalsIcon, PositionsIcon, CandidatesIcon,
  AccumulationIcon, StrategyIcon, CalibrationIcon, PostmortemIcon,
  GlossaryIcon, LogOutIcon,
} from '../icons'

const NAV = [
  { to: '/',             label: 'Dashboard',    Icon: DashboardIcon },
  { to: '/signals',      label: 'Signals',      Icon: SignalsIcon },
  { to: '/positions',    label: 'Positions',    Icon: PositionsIcon },
  { to: '/candidates',   label: 'Candidates',   Icon: CandidatesIcon },
  { to: '/accumulation', label: 'Accumulation', Icon: AccumulationIcon },
  { to: '/strategy-lab', label: 'Strategy Lab', Icon: StrategyIcon },
  { to: '/calibration',  label: 'Calibration',  Icon: CalibrationIcon },
  { to: '/postmortem',   label: 'Postmortem',   Icon: PostmortemIcon },
  { to: '/glossary',     label: 'Glossary',     Icon: GlossaryIcon },
]

export default function Sidebar() {
  const clearToken = useAuthStore(s => s.clearToken)

  return (
    <nav style={{
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      width: 220,
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      height: '100%',
    }}>
      {/* Logo */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '0 20px',
        height: 52,
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <span style={{ color: 'var(--green)', fontSize: 18, fontWeight: 700 }}>▲</span>
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.02em' }}>Plutus</span>
      </div>

      {/* Nav */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 8px' }}>
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 12px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: isActive ? 600 : 400,
              color: isActive ? 'var(--green)' : 'var(--muted)',
              background: isActive ? 'rgba(0,200,150,0.07)' : 'transparent',
              textDecoration: 'none',
              marginBottom: 1,
              borderLeft: `2px solid ${isActive ? 'var(--green)' : 'transparent'}`,
            })}>
            <Icon size={15} />
            {label}
          </NavLink>
        ))}
      </div>

      {/* Sign out */}
      <button
        onClick={clearToken}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 20px',
          borderTop: '1px solid var(--border)',
          color: 'var(--dim)',
          fontSize: 12,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          width: '100%',
          textAlign: 'left',
        }}
        onMouseEnter={e => (e.currentTarget.style.color = 'var(--red)')}
        onMouseLeave={e => (e.currentTarget.style.color = 'var(--dim)')}>
        <LogOutIcon size={14} />
        Sign out
      </button>
    </nav>
  )
}
