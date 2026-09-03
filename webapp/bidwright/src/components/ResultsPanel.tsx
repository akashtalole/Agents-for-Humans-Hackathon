import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { RunFile, RunStatus } from "../api";
import { fetchRunFile, runFileUrl } from "../api";

interface ResultsPanelProps {
  jobId: string;
  run: RunStatus;
}

const UNVERIFIED_TAB = "Agent's Own Summary (unverified)";

export function ResultsPanel({ jobId, run }: ResultsPanelProps) {
  const files = run.files ?? [];
  const tabLabels = [...files.map((f) => f.label), UNVERIFIED_TAB];
  const [activeTab, setActiveTab] = useState(0);

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      {run.status_badge && <StatusBanner level={run.status_badge.level} message={run.status_badge.message} />}
      {run.status === "failed" && (
        <div className="rounded-t-xl bg-red-50 px-5 py-3 text-sm font-medium text-red-800 dark:bg-red-950/40 dark:text-red-300">
          Run failed: {run.error ?? "unknown error"}
        </div>
      )}

      <div className="flex flex-wrap gap-1 border-b border-slate-200 px-3 pt-3 dark:border-slate-800">
        {tabLabels.map((label, i) => (
          <button
            key={label}
            type="button"
            onClick={() => setActiveTab(i)}
            className={`rounded-t-lg px-3 py-2 text-sm font-medium transition ${
              activeTab === i
                ? "border-b-2 border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="p-5">
        {activeTab < files.length ? (
          <FileTab jobId={jobId} file={files[activeTab]} />
        ) : (
          <SummaryTab summaryText={run.summary_text} />
        )}
      </div>
    </div>
  );
}

function StatusBanner({ level, message }: { level: "error" | "warning" | "success"; message: string }) {
  const styles: Record<string, string> = {
    error: "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-300",
    warning: "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
    success: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  };
  const icons: Record<string, string> = { error: "⚠️", warning: "⚠️", success: "✅" };
  return (
    <div className={`rounded-t-xl px-5 py-3 text-sm font-semibold ${styles[level]}`}>
      {icons[level]} {message}
    </div>
  );
}

function FileTab({ jobId, file }: { jobId: string; file: RunFile }) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setContent(null);
    setError(null);
    fetchRunFile(jobId, file.name)
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, file.name]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          <DownloadButton href={runFileUrl(jobId, file.name)} filename={file.name} label={`Download ${file.name}`} />
          {file.download && (
            <DownloadButton
              href={runFileUrl(jobId, file.download.name)}
              filename={file.download.name}
              label={file.download.label}
            />
          )}
        </div>
      </div>
      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400">Could not load {file.name}: {error}</p>
      ) : content === null ? (
        <p className="text-sm text-slate-400">Loading&hellip;</p>
      ) : (
        <div className="markdown-body">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

function SummaryTab({ summaryText }: { summaryText: string | null }) {
  return (
    <div>
      <p className="mb-4 rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-400">
        This is the orchestrator's own free-text reply, shown for transparency. It can occasionally misstate
        specifics even when every generated file above is correct - treat <strong>Decisions Needed</strong> and the
        generated files as the source of truth, not this tab.
      </p>
      <div className="markdown-body">
        <ReactMarkdown>{summaryText ?? "_Not available._"}</ReactMarkdown>
      </div>
    </div>
  );
}

function DownloadButton({ href, filename, label }: { href: string; filename: string; label: string }) {
  return (
    <a
      href={href}
      download={filename}
      className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
    >
      ⬇ {label}
    </a>
  );
}
