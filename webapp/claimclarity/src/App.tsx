import { useCallback, useEffect, useRef, useState } from 'react'
import { createRun, fetchRun, fetchStatus, runEventsUrl } from './api'
import ActivityLog from './components/ActivityLog'
import ApprovalPanel from './components/ApprovalPanel'
import ChatPanel from './components/ChatPanel'
import Header from './components/Header'
import InputPanel from './components/InputPanel'
import ResultsTabs from './components/ResultsTabs'
import StatusBanner from './components/StatusBanner'
import { useTheme } from './hooks/useTheme'
import type { RunStatusResponse, StatusResponse } from './types'

export default function App() {
  const [theme, toggleTheme] = useTheme()
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)

  const [jobId, setJobId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [logLines, setLogLines] = useState<string[]>([])
  const [result, setResult] = useState<RunStatusResponse | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    fetchStatus()
      .then(setStatus)
      .catch((err) => setStatusError(err instanceof Error ? err.message : String(err)))
  }, [])

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  const stopEvents = useCallback(() => {
    eventSourceRef.current?.close()
    eventSourceRef.current = null
  }, [])

  useEffect(() => stopEvents, [stopEvents])
  useEffect(() => stopPolling, [stopPolling])

  const finish = useCallback(
    async (id: string) => {
      try {
        const body = await fetchRun(id)
        setResult(body)
        if (body.status === 'running') return
        setRunning(false)
        stopPolling()
        stopEvents()
        if (body.status === 'failed') {
          setRunError(body.error ?? 'The run failed for an unknown reason.')
        }
      } catch (err) {
        setRunning(false)
        stopPolling()
        stopEvents()
        setRunError(err instanceof Error ? err.message : String(err))
      }
    },
    [stopPolling, stopEvents],
  )

  const handleRun = useCallback(
    async (useExample: boolean, files: File[]) => {
      setRunError(null)
      setResult(null)
      setLogLines([])
      setRunning(true)
      stopPolling()
      stopEvents()

      let id: string
      try {
        const created = await createRun(useExample, files)
        id = created.job_id
      } catch (err) {
        setRunning(false)
        setRunError(err instanceof Error ? err.message : String(err))
        return
      }
      setJobId(id)

      const source = new EventSource(runEventsUrl(id))
      eventSourceRef.current = source
      source.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data)
          if (typeof data.tool === 'string') {
            setLogLines((prev) => (prev[prev.length - 1] === data.tool ? prev : [...prev, data.tool]))
          }
          if (data.done) {
            finish(id)
          }
        } catch {
          // ignore malformed event
        }
      }
      source.onerror = () => {
        // SSE dropped (e.g. proxy hiccup) - the poller below is the
        // resilience backup that still gets us to a final result.
        stopEvents()
      }

      // Resilience backup / source of truth for the final result: poll the
      // status endpoint regardless of whether the SSE stream stays open.
      pollTimer.current = setInterval(() => finish(id), 1500)
    },
    [finish, stopEvents, stopPolling],
  )

  return (
    <div className="flex min-h-full flex-col">
      <Header status={status} statusError={statusError} theme={theme} onToggleTheme={toggleTheme} />

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
        <InputPanel running={running} onRun={handleRun} />

        {running && <ActivityLog lines={logLines} running={running} />}

        {runError && (
          <div className="rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
            <p className="font-semibold">The run failed.</p>
            <p className="mt-1 font-mono text-xs">{runError}</p>
          </div>
        )}

        {!running && result?.status === 'awaiting_approval' && jobId && (
          <>
            <ApprovalPanel
              jobId={jobId}
              draftText={result.draft_text ?? ''}
              review={result.review}
              guardrail={result.guardrail}
              onResolved={setResult}
            />
            <ChatPanel jobId={jobId} />
          </>
        )}

        {!running && result?.status === 'rejected' && jobId && (
          <>
            {result.status_badge && <StatusBanner badge={result.status_badge} />}
            <RejectedView reason={result.reject_reason} draftText={result.draft_text} />
          </>
        )}

        {!running && result?.status === 'completed' && jobId && (
          <>
            {result.status_badge && <StatusBanner badge={result.status_badge} />}
            <ResultsTabs jobId={jobId} files={result.files ?? []} summaryText={result.summary_text ?? ''} />
            <ChatPanel jobId={jobId} />
          </>
        )}

        {!running && !result && !runError && (
          <p className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
            Choose claim documents above, then click <strong>Run ClaimClarity</strong>.
          </p>
        )}
      </main>

      <footer className="mx-auto w-full max-w-5xl px-4 pb-8 pt-2 text-center text-xs text-slate-400 sm:px-6 dark:text-slate-600">
        ClaimClarity drafts; it does not submit. A human always reviews, signs, and sends the appeal.
      </footer>
    </div>
  )
}

function RejectedView({ reason, draftText }: { reason: string | null; draftText: string | null }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        This appeal was rejected
      </h2>
      <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
        {reason ? (
          <>
            <span className="font-medium">Reason given:</span> {reason}
          </>
        ) : (
          <span className="italic text-slate-500 dark:text-slate-400">No reason was given.</span>
        )}
      </p>
      {draftText && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Draft at time of rejection (read-only)
          </p>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 font-mono text-xs text-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
            {draftText}
          </pre>
        </div>
      )}
    </section>
  )
}
