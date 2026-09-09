import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { RiskLevel } from '../types'

/** Free text authored by a model. Models emit Markdown whether or not you
 * ask them to, so rendering these fields as plain text leaks literal `**`
 * into the UI. Use this for narrative/rationale prose only - never for a
 * broadcast counter-message, which must be shown exactly as the guardrail
 * scanned it. */
export function Prose({ children, className = '' }: { children: string; className?: string }) {
  return (
    <div
      className={`prose prose-invert prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-strong:text-slate-200 ${className}`}
    >
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-white/[0.03] p-5 shadow-xl shadow-black/20 backdrop-blur ${className}`}>
      {children}
    </div>
  )
}

export function SectionTitle({ eyebrow, title, hindi }: { eyebrow: string; title: string; hindi?: string }) {
  return (
    <div className="mb-6">
      <div className="text-xs font-semibold uppercase tracking-widest text-saffron-400">{eyebrow}</div>
      <h1 className="mt-1 flex items-baseline gap-3 text-2xl font-semibold text-white">
        {title}
        {hindi && <span className="text-base font-normal text-slate-500">{hindi}</span>}
      </h1>
    </div>
  )
}

const RISK_STYLES: Record<RiskLevel, string> = {
  routine: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  elevated: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  critical: 'bg-red-500/15 text-red-300 border-red-500/30',
}

export function RiskBadge({ level, className = '' }: { level: RiskLevel; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${RISK_STYLES[level]} ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {level}
    </span>
  )
}

export const RISK_COLOR: Record<RiskLevel, string> = {
  routine: '#34d399',
  elevated: '#fbbf24',
  critical: '#f87171',
}

export function riskFromPct(pct: number): RiskLevel {
  if (pct >= 110) return 'critical'
  if (pct >= 85) return 'elevated'
  return 'routine'
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  type = 'button',
  className = '',
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  type?: 'button' | 'submit'
  className?: string
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-saffron-500 to-saffron-600 px-4 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:from-saffron-400 hover:to-saffron-500 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none ${className}`}
    >
      {children}
    </button>
  )
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">{children}</label>
}

export const inputClass =
  'w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-saffron-400/60 focus:outline-none focus:ring-1 focus:ring-saffron-400/40'
