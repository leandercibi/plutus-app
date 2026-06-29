type IconProps = { size?: number; className?: string }

const I = ({ d, size = 16, ...p }: IconProps & { d: string }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" {...p}>
    <path d={d} />
  </svg>
)

export const DashboardIcon = (p: IconProps) => (
  <I {...p} d="M1 1h6v6H1V1Zm8 0h6v6H9V1ZM1 9h6v6H1V9Zm8 0h6v6H9V9Z" />
)

export const SignalsIcon = (p: IconProps) => (
  <I {...p} d="M9 1 3 9h4.5L6 15l7-9H8.5L9 1Z" />
)

export const PositionsIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1.5" y="4.5" width="13" height="10" rx="1.5" />
    <path d="M5 4.5V3A1.5 1.5 0 0 1 6.5 1.5h3A1.5 1.5 0 0 1 11 3v1.5M6 9.5l1.5 1.5L11 7" />
  </svg>
)

export const CandidatesIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="6.5" cy="6.5" r="4.5" />
    <path d="m10 10 4 4" />
  </svg>
)

export const AccumulationIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 4.5 8 2l6 2.5-6 2.5-6-2.5ZM2 8l6 2.5L14 8M2 11.5 8 14l6-2.5" />
  </svg>
)

export const StrategyIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 1.5v7L1.5 13a.75.75 0 0 0 .65 1.12h11.7a.75.75 0 0 0 .65-1.12L11 8.5v-7M5 1.5h6M5 1.5H4m7 0h1" />
  </svg>
)

export const CalibrationIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M1 4h2m8 0h4M1 12h7m3 0h4M5 2v4m6 6v4" />
    <circle cx="5" cy="4" r="1.5" fill="currentColor" />
    <circle cx="11" cy="12" r="1.5" fill="currentColor" />
  </svg>
)

export const PostmortemIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2.5" y="1.5" width="11" height="13" rx="1.5" />
    <path d="M5 5.5h6M5 8.5h6M5 11.5h3.5" />
  </svg>
)

export const GlossaryIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 1.5h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H3m0-13v13M3 1.5H2" />
    <path d="M6 5.5h4.5M6 8.5h3" />
  </svg>
)

export const ChevronDownIcon = (p: IconProps) => (
  <I {...p} d="m3 5 5 5 5-5" />
)

export const PlayIcon = (p: IconProps) => (
  <I {...p} d="M3 2.5v11l10-5.5-10-5.5Z" />
)

export const XIcon = (p: IconProps) => (
  <I {...p} d="m2 2 12 12M14 2 2 14" />
)

export const CheckIcon = (p: IconProps) => (
  <I {...p} d="m2 8 4.5 5L14 3" />
)

export const PauseIcon = (p: IconProps) => (
  <I {...p} d="M4 2h2v12H4V2Zm6 0h2v12h-2V2Z" />
)

export const LogOutIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 2H3a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3M10.5 11 14 8l-3.5-3M14 8H6" />
  </svg>
)

export const RefreshIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 8A7 7 0 0 1 13.5 4m1.5-.5v4h-4M15 8A7 7 0 0 1 2.5 12m-1.5.5v-4h4" />
  </svg>
)

export const ClockIcon = (p: IconProps) => (
  <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="8" cy="8" r="6.5" />
    <path d="M8 4.5V8l2.5 2.5" />
  </svg>
)
