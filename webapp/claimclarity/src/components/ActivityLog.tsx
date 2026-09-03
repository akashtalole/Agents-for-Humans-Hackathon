import { useEffect, useRef } from 'react'

interface Props {
  lines: string[]
  running: boolean
}

export default function ActivityLog({ lines, running }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [lines])

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-2">
        {running && (
          <svg className="h-4 w-4 animate-spin text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {running
            ? 'ClaimClarity is analyzing the claim, checking codes, and investigating the denial…'
            : 'Agent activity log'}
        </h2>
      </div>
      <div
        className="activity-log h-56 overflow-y-auto rounded-lg bg-slate-950 p-3 font-mono text-xs text-emerald-300"
        aria-live="polite"
      >
        {lines.length === 0 ? (
          <p className="text-slate-500">Waiting for the first tool call…</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap py-0.5">
              🔧 calling <span className="text-teal-300">`{line}`</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </section>
  )
}
