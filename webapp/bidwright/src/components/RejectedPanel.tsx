import type { RunStatus } from "../api";

interface RejectedPanelProps {
  run: RunStatus;
}

export function RejectedPanel({ run }: RejectedPanelProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="rounded-t-xl bg-red-50 px-5 py-3 text-sm font-semibold text-red-800 dark:bg-red-950/40 dark:text-red-300">
        ✕ Rejected — not approved for submission.
      </div>
      <div className="space-y-4 p-5">
        <div className="rounded-lg bg-red-50/60 px-4 py-3 text-sm text-red-900 dark:bg-red-950/20 dark:text-red-200">
          <span className="font-semibold">Reason: </span>
          {run.reject_reason ? run.reject_reason : <em>No reason was given.</em>}
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-50">
            Draft at time of rejection (read-only, for reference)
          </h3>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
            {run.draft_text ?? "_No draft available._"}
          </pre>
        </div>
      </div>
    </div>
  );
}
