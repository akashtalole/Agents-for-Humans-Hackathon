import { useState } from "react";
import type { RunStatus } from "../api";
import { approveRun, rejectRun } from "../api";

interface ApprovalPanelProps {
  jobId: string;
  run: RunStatus;
  onUpdated: (run: RunStatus) => void;
}

export function ApprovalPanel({ jobId, run, onUpdated }: ApprovalPanelProps) {
  const [draft, setDraft] = useState(run.draft_text ?? "");
  const [acknowledged, setAcknowledged] = useState(false);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const findings = run.guardrail?.findings ?? [];
  const requiresAck = findings.length > 0;
  const issues = run.review?.issues ?? [];

  async function handleApprove() {
    setError(null);
    setBusy(true);
    try {
      const updated = await approveRun(jobId, draft);
      onUpdated(updated);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    setError(null);
    setBusy(true);
    try {
      const updated = await rejectRun(jobId, rejectReason.trim() || undefined);
      onUpdated(updated);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="rounded-t-xl bg-amber-50 px-5 py-3 text-sm font-semibold text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
        ⚠️ Awaiting your approval before this proposal is final.
      </div>

      <div className="space-y-5 p-5">
        <ReviewSection issues={issues} />
        {requiresAck && <GuardrailSection findings={findings} />}

        <div>
          <label htmlFor="draft-text" className="mb-2 block text-sm font-semibold text-slate-900 dark:text-slate-50">
            Proposal draft (editable before approval)
          </label>
          <textarea
            id="draft-text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={16}
            className="w-full rounded-lg border border-slate-300 bg-white p-3 font-mono text-xs text-slate-800 shadow-inner focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          />
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </p>
        )}

        {requiresAck && (
          <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 dark:border-slate-600"
            />
            I've reviewed the flagged issue(s) above and approve anyway.
          </label>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handleApprove}
            disabled={busy || (requiresAck && !acknowledged)}
            className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ✓ Approve
          </button>
          <button
            type="button"
            onClick={() => setShowRejectForm((v) => !v)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 shadow-sm transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-950/40"
          >
            ✕ Reject
          </button>
        </div>

        {showRejectForm && (
          <div className="rounded-lg border border-red-200 bg-red-50/50 p-4 dark:border-red-900 dark:bg-red-950/20">
            <label htmlFor="reject-reason" className="mb-2 block text-sm font-medium text-slate-800 dark:text-slate-200">
              Why is this being rejected? (optional)
            </label>
            <textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
              placeholder="e.g. Pricing section needs revision, wrong point of contact&hellip;"
              className="mb-3 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-800 focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
            />
            <button
              type="button"
              onClick={handleReject}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Confirm reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewSection({ issues }: { issues: string[] }) {
  if (issues.length === 0) {
    return (
      <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
        ✅ Reviewer found no issues with this draft.
      </div>
    );
  }
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">Reviewer issues</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-300">
        {issues.map((issue, i) => (
          <li key={i}>{issue}</li>
        ))}
      </ul>
    </div>
  );
}

function GuardrailSection({ findings }: { findings: { rule: string; excerpt: string; explanation: string }[] }) {
  return (
    <div className="rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
      <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-red-900 dark:text-red-200">
        🚩 Guardrail flagged {findings.length} finding{findings.length === 1 ? "" : "s"}
      </h3>
      <div className="space-y-3">
        {findings.map((f, i) => (
          <div key={i} className="rounded-md bg-white/70 p-3 text-sm shadow-sm dark:bg-slate-950/40">
            <p className="mb-1 font-mono text-xs font-semibold uppercase tracking-wide text-red-700 dark:text-red-400">
              {f.rule}
            </p>
            <blockquote className="mb-1 border-l-2 border-red-300 pl-2 italic text-slate-700 dark:border-red-800 dark:text-slate-300">
              "{f.excerpt}"
            </blockquote>
            <p className="text-slate-800 dark:text-slate-200">{f.explanation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
