import { useEffect, useRef, useState } from 'react'
import { createRun, fetchRun, fetchStatus, watchRunEvents } from './api'
import DisclaimerBanner from './components/DisclaimerBanner'
import Header from './components/Header'
import ResultsTabs from './components/ResultsTabs'
import RunPanel from './components/RunPanel'
import StatusBadgeBanner from './components/StatusBadgeBanner'
import { useTheme } from './hooks/useTheme'
import type { RunStatusResponse, StatusResponse } from './types'

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [result, setResult] = useState<RunStatusResponse | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const logEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    fetchStatus()
      .then(setStatus)
      .catch(() =>
        setStatus({
          status_text: 'Could not reach the GlacierWatch API',
          ready: false,
          disclaimer:
            '**This is a decision-support triage tool, not a prediction system.** ' +
            '(Disclaimer could not be loaded from the server - see /api/status.)',
        }),
      )
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log])

  const handleRun = async () => {
    setRunning(true)
    setLog([])
    setResult(null)
    setRunError(null)
    try {
      const { job_id } = await createRun()
      setJobId(job_id)

      watchRunEvents(
        job_id,
        (tool) => setLog((prev) => [...prev, `🔧 calling \`${tool}\``]),
        () => {
          fetchRun(job_id)
            .then((data) => {
              setResult(data)
              if (data.status === 'failed') {
                setRunError(data.error ?? 'The run failed for an unknown reason.')
              }
            })
            .catch(() => setRunError('Could not fetch the run result.'))
            .finally(() => setRunning(false))
        },
      )
    } catch {
      setRunError('Could not start a GlacierWatch run - is the API reachable?')
      setRunning(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <Header status={status} theme={theme} onToggleTheme={toggleTheme} />
      <DisclaimerBanner text={status?.disclaimer ?? null} />

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
        <RunPanel
          ready={status?.ready ?? false}
          running={running}
          onRun={handleRun}
          log={log}
          logEndRef={logEndRef}
        />

        {runError && (
          <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm font-medium text-red-900 dark:border-red-800 dark:bg-red-950/50 dark:text-red-200">
            ⚠️ {runError}
          </div>
        )}

        {result && result.status === 'completed' && result.status_badge && (
          <>
            <StatusBadgeBanner badge={result.status_badge} />
            <ResultsTabs
              jobId={jobId as string}
              sites={result.sites ?? []}
              files={result.files ?? []}
              summaryText={result.summary_text ?? '_Not available._'}
            />
          </>
        )}

        {!running && !result && !runError && (
          <p className="text-center text-sm text-slate-500 dark:text-slate-400">
            Click <strong>Run GlacierWatch</strong> above to generate this week's watchlist.
          </p>
        )}
      </main>

      <footer className="mx-auto max-w-5xl px-4 pb-8 pt-2 text-center text-xs text-slate-400 dark:text-slate-600 sm:px-6">
        GlacierWatch is decision support for prioritizing monitoring attention — it never predicts
        if, when, or where an avalanche or glacial lake outburst flood will occur.
      </footer>
    </div>
  )
}
