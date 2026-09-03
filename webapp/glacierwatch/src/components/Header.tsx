import type { StatusResponse } from '../types'

function StatusPill({ status }: { status: StatusResponse | null }) {
  if (!status) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white/70">
        <span className="h-1.5 w-1.5 rounded-full bg-white/40" />
        Checking model status…
      </span>
    )
  }
  const dotColor = status.ready ? 'bg-emerald-400' : 'bg-red-400'
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white"
      title={status.status_text}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      {status.status_text}
    </span>
  )
}

export default function Header({
  status,
  theme,
  onToggleTheme,
}: {
  status: StatusResponse | null
  theme: 'light' | 'dark'
  onToggleTheme: () => void
}) {
  return (
    <header className="bg-gradient-to-r from-sky-600 to-slate-700 text-white">
      <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            <span aria-hidden="true">🏔️</span> GlacierWatch
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-sky-100">
            Combines published, cited Himalayan glacial-hazard assessments with live weather and
            seismic data to prioritize monitoring attention this week.
          </p>
        </div>
        <div className="flex items-center gap-3 sm:flex-col sm:items-end sm:gap-2">
          <StatusPill status={status} />
          <button
            type="button"
            onClick={onToggleTheme}
            className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white transition hover:bg-white/20"
            aria-label="Toggle light/dark mode"
          >
            {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
          </button>
        </div>
      </div>
    </header>
  )
}
