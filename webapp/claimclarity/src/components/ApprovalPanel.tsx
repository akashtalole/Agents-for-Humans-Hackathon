import { useState } from 'react'
import { approveRun, rejectRun } from '../api'
import type { GuardrailResult, ReviewResult, RunStatusResponse } from '../types'

interface Props {
  jobId: string
  draftText: string
  review: ReviewResult | null
  guardrail: GuardrailResult | null
  onResolved: (result: RunStatusResponse) => void
}

export default function ApprovalPanel({ jobId, draftText, review, guardrail, onResolved }: Props) {
  const [editedText, setEditedText] = useState(draftText)
  const [acknowledged, setAcknowledged] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasGuardrailFindings = !!guardrail && !guardrail.passed && guardrail.findings.length > 0
  const canApprove = !busy && (!hasGuardrailFindings || acknowledged)

  const handleApprove = async () => {
    setBusy(true)
    setError(null)
    try {
      const edited = editedText !== draftText ? editedText : null
      const result = await approveRun(jobId, edited)
      onResolved(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const handleReject = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await rejectRun(jobId, reason.trim() || null)
      onResolved(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-xl border border-amber-300 bg-amber-50/60 shadow-sm dark:border-amber-900 dark:bg-amber-950/20">
      <div className="border-b border-amber-200 px-5 py-4 dark:border-amber-900">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
          ⚠️ Review before sending
        </h2>
        <p className="mt-1 text-sm text-amber-900/80 dark:text-amber-200/70">
          ClaimClarity drafts; it does not submit. Read the review and guardrail findings below, edit the
          letter if you want, then approve or reject it.
        </p>
      </div>

      <div className="space-y-5 p-5">
        <ReviewSummary review={review} />
        {guardrail && <GuardrailFindings guardrail={guardrail} />}

        <div>
          <label htmlFor="draft-editor" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Appeal package (editable)
          </label>
          <textarea
            id="draft-editor"
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            rows={14}
            disabled={busy || rejecting}
            className="w-full rounded-lg border border-slate-300 bg-white p-3 font-mono text-xs text-slate-800 shadow-inner focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          />
        </div>

        {hasGuardrailFindings && (
          <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              disabled={busy || rejecting}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
            />
            <span>
              I&apos;ve read the guardrail finding(s) above and reviewed/edited the letter accordingly before
              approving.
            </span>
          </label>
        )}

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        {!rejecting ? (
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleApprove}
              disabled={!canApprove}
              className="rounded-lg bg-gradient-to-r from-teal-600 to-emerald-600 px-4 py-2 font-semibold text-white shadow transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:brightness-100"
            >
              {busy ? 'Approving…' : '✅ Approve'}
            </button>
            <button
              type="button"
              onClick={() => setRejecting(true)}
              disabled={busy}
              className="rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40"
            >
              ✖ Reject
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-red-200 bg-red-50/60 p-3 dark:border-red-900 dark:bg-red-950/20">
            <label htmlFor="reject-reason" className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Why are you rejecting this appeal? (optional)
            </label>
            <textarea
              id="reject-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              disabled={busy}
              className="w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-800 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
              placeholder="e.g. tone is too aggressive, wrong facts, want to consult an advocate first…"
            />
            <div className="mt-3 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleReject}
                disabled={busy}
                className="rounded-lg bg-red-600 px-4 py-2 font-semibold text-white shadow transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? 'Rejecting…' : 'Confirm reject'}
              </button>
              <button
                type="button"
                onClick={() => setRejecting(false)}
                disabled={busy}
                className="rounded-lg border border-slate-300 px-4 py-2 font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

function ReviewSummary({ review }: { review: ReviewResult | null }) {
  if (!review) {
    return (
      <p className="text-sm italic text-slate-500 dark:text-slate-400">
        No independent review result available for this run.
      </p>
    )
  }
  if (review.approved) {
    return (
      <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
        <p className="font-semibold">✅ Independent review found no issues.</p>
        <p className="mt-1 text-emerald-900/80 dark:text-emerald-200/70">{review.summary}</p>
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
      <p className="font-semibold">Independent review flagged {review.issues.length} issue(s):</p>
      <ul className="mt-1.5 list-disc space-y-1 pl-5">
        {review.issues.map((issue, i) => (
          <li key={i}>{issue}</li>
        ))}
      </ul>
      <p className="mt-2 text-amber-900/70 dark:text-amber-200/60">{review.summary}</p>
    </div>
  )
}

function GuardrailFindings({ guardrail }: { guardrail: GuardrailResult }) {
  if (guardrail.passed || guardrail.findings.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
        ✅ Guardrail check passed — no guaranteed-outcome claims, unsupported medical claims, or legal
        advice found.
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
      <p className="font-semibold">🚩 Guardrail check found {guardrail.findings.length} finding(s):</p>
      <ul className="mt-2 space-y-2">
        {guardrail.findings.map((finding, i) => (
          <li key={i} className="rounded border border-red-200 bg-white/60 p-2 dark:border-red-800 dark:bg-red-950/30">
            <p className="font-mono text-xs uppercase tracking-wide text-red-600 dark:text-red-400">
              {finding.rule}
            </p>
            <p className="mt-1 italic text-red-800 dark:text-red-200">&ldquo;{finding.excerpt}&rdquo;</p>
            <p className="mt-1 text-red-900/80 dark:text-red-200/70">{finding.explanation}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
