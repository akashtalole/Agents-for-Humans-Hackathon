import type { StatusResponse } from '../types'

interface Props {
  status: StatusResponse | null
  statusError: string | null
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}

export default function Header({ status, statusError, theme, onToggleTheme }: Props) {
  return (
    <header className="bg-gradient-to-r from-teal-600 to-emerald-600 text-white shadow-md">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
            <span aria-hidden="true">🩺</span> ClaimClarity
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-teal-50/90 sm:text-base">
            An agent that reads your insurance denial, checks it against real ICD-10 coding rules and
            your plan&apos;s own terms, and drafts the appeal — or tells you honestly when it&apos;s not
            worth fighting.
          </p>
        </div>
        <div className="flex items-center gap-3 sm:flex-col sm:items-end">
          <ModelStatusPill status={status} statusError={statusError} />
          <button
            type="button"
            onClick={onToggleTheme}
            className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium text-white ring-1 ring-white/30 transition hover:bg-white/25"
            aria-label="Toggle light/dark mode"
          >
            {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
          </button>
        </div>
      </div>
    </header>
  )
}

function ModelStatusPill({ status, statusError }: { status: StatusResponse | null; statusError: string | null }) {
  if (statusError) {
    return (
      <span className="rounded-full bg-red-500/20 px-3 py-1 text-xs font-medium text-white ring-1 ring-red-200/50">
        Status unavailable: {statusError}
      </span>
    )
  }
  if (!status) {
    return (
      <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white ring-1 ring-white/30">
        Checking model status…
      </span>
    )
  }
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ${
        status.ready
          ? 'bg-white/15 text-white ring-white/30'
          : 'bg-amber-400/90 text-amber-950 ring-amber-200'
      }`}
      title={status.status_text}
    >
      {status.ready ? '● ' : '⚠ '}
      {status.status_text}
    </span>
  )
}
