export default function RunPanel({
  ready,
  running,
  onRun,
  log,
  logEndRef,
}: {
  ready: boolean
  running: boolean
  onRun: () => void
  log: string[]
  logEndRef: React.RefObject<HTMLDivElement | null>
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Reference watchlist
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600 dark:text-slate-400">
            GlacierWatch runs against a small, cited set of documented Himalayan glacial hazard
            sites bundled with this tool. It fetches live weather (Open-Meteo) and seismic (USGS)
            data for each site at run time — there's no file to upload.
          </p>
        </div>
        <button
          type="button"
          onClick={onRun}
          disabled={!ready || running}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white shadow transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
        >
          {running ? (
            <>
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
              />
              Running…
            </>
          ) : (
            'Run GlacierWatch'
          )}
        </button>
      </div>

      {(running || log.length > 0) && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Agent activity
          </p>
          <div className="max-h-56 overflow-y-auto rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-100">
            {log.length === 0 ? (
              <p className="text-slate-400">Starting…</p>
            ) : (
              log.map((line, i) => <div key={i}>{line}</div>)
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </section>
  )
}
