import { useMemo, useState } from 'react'
import { approveRun, rejectRun } from '../api'
import type { AlertForApproval, GuardrailVerdict, ReviewVerdict, RunStatusResponse } from '../types'

/** The human-in-the-loop approval gate for this run's whole batch of
 * community alert bulletins (glacierwatch/api.py's /approve and /reject).
 * Deliberately a single batch action, not one approval per site - a run's
 * alerts are reviewed and guardrail-checked together, so they're approved
 * or rejected together too. Shown only while status === "awaiting_approval". */
export default function ApprovalPanel({
  jobId,
  alerts,
  reviews,
  guardrails,
  onResolved,
}: {
  jobId: string
  alerts: AlertForApproval[]
  reviews: Record<string, ReviewVerdict> | null
  guardrails: Record<string, GuardrailVerdict> | null
  onResolved: (result: RunStatusResponse) => void
}) {
  const [texts, setTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(alerts.map((a) => [a.site_id, a.text])),
  )
  const [acknowledged, setAcknowledged] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const anyGuardrailFindings = useMemo(
    () => Object.values(guardrails ?? {}).some((g) => g.findings.length > 0),
    [guardrails],
  )
  const totalGuardrailFindings = useMemo(
    () => Object.values(guardrails ?? {}).reduce((n, g) => n + g.findings.length, 0),
    [guardrails],
  )

  const handleApprove = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await approveRun(jobId, texts)
      onResolved(result)
    } catch {
      setError('Could not submit approval - is the API reachable?')
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await rejectRun(jobId, rejectReason.trim() || null)
      onResolved(result)
    } catch {
      setError('Could not submit rejection - is the API reachable?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-5 rounded-xl border border-amber-300 bg-amber-50/60 p-5 dark:border-amber-800 dark:bg-amber-950/20">
      <div>
        <h2 className="text-lg font-semibold text-amber-950 dark:text-amber-100">
          {alerts.length} community alert bulletin{alerts.length === 1 ? '' : 's'} awaiting your approval
        </h2>
        <p className="mt-1 text-sm text-amber-900/80 dark:text-amber-200/80">
          These are the plain-language bulletins drafted for downstream village committees. Review each
          one, edit if needed, then approve or reject the whole batch below. Nothing here has been sent to
          anyone yet.
        </p>
      </div>

      <div className="space-y-6">
        {alerts.map((alert) => {
          const review = reviews?.[alert.site_id]
          const guardrail = guardrails?.[alert.site_id]
          return (
            <div
              key={alert.site_id}
              className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
            >
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{alert.site_name}</h3>

              {review && (
                <div
                  className={`rounded-md border px-3 py-2 text-sm ${
                    review.approved
                      ? 'border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200'
                      : 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
                  }`}
                >
                  <p className="font-medium">
                    {review.approved ? '✅ Reviewer: no issues found' : '⚠️ Reviewer found issues'}
                  </p>
                  {review.issues.length > 0 && (
                    <ul className="mt-1 list-disc space-y-0.5 pl-5">
                      {review.issues.map((issue, i) => (
                        <li key={i}>{issue}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {guardrail && guardrail.findings.length > 0 && (
                <div className="rounded-md border border-red-400 bg-red-50 px-3 py-2 text-sm text-red-950 dark:border-red-800 dark:bg-red-950/50 dark:text-red-200">
                  <p className="font-semibold">
                    🚨 Guardrail flagged {guardrail.findings.length} prediction-language finding
                    {guardrail.findings.length === 1 ? '' : 's'}
                  </p>
                  <ul className="mt-1.5 space-y-1.5">
                    {guardrail.findings.map((f, i) => (
                      <li key={i}>
                        <span className="font-mono text-xs">&quot;{f.excerpt}&quot;</span> — {f.explanation}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {guardrail && guardrail.findings.length === 0 && (
                <p className="text-xs text-emerald-700 dark:text-emerald-400">
                  ✅ Guardrail: no prediction-language findings
                </p>
              )}

              <label className="block text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Bulletin text (editable before approval)
              </label>
              <textarea
                value={texts[alert.site_id]}
                onChange={(e) => setTexts((prev) => ({ ...prev, [alert.site_id]: e.target.value }))}
                rows={10}
                className="w-full rounded-md border border-slate-300 bg-slate-50 p-3 font-mono text-xs text-slate-800 focus:border-sky-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              />
            </div>
          )
        })}
      </div>

      {error && (
        <p className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/50 dark:text-red-200">
          {error}
        </p>
      )}

      {anyGuardrailFindings && (
        <label className="flex items-start gap-2 rounded-md border border-red-400 bg-red-50 px-3 py-2.5 text-sm text-red-950 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            I have reviewed the {totalGuardrailFindings} guardrail finding{totalGuardrailFindings === 1 ? '' : 's'}{' '}
            above and edited or accepted the bulletin text accordingly before approving.
          </span>
        </label>
      )}

      {!rejecting ? (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handleApprove}
            disabled={busy || (anyGuardrailFindings && !acknowledged)}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'Submitting…' : `Approve All (${alerts.length})`}
          </button>
          <button
            type="button"
            onClick={() => setRejecting(true)}
            disabled={busy}
            className="rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 shadow-sm transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-950/40"
          >
            Reject All
          </button>
        </div>
      ) : (
        <div className="space-y-2 rounded-md border border-red-300 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950/30">
          <label className="block text-xs font-medium uppercase tracking-wide text-red-800 dark:text-red-300">
            Reason for rejection (optional)
          </label>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-red-300 bg-white p-2 text-sm text-slate-800 focus:border-red-500 focus:outline-none dark:border-red-700 dark:bg-slate-900 dark:text-slate-200"
            placeholder="e.g. needs local-language review before this can go out"
          />
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleReject}
              disabled={busy}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Submitting…' : 'Confirm Reject All'}
            </button>
            <button
              type="button"
              onClick={() => setRejecting(false)}
              disabled={busy}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
