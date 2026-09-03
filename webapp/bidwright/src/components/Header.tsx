import type { StatusResponse } from "../api";

interface HeaderProps {
  status: StatusResponse | null;
  statusError: boolean;
  theme: "light" | "dark";
  onToggleTheme: () => void;
}

export function Header({ status, statusError, theme, onToggleTheme }: HeaderProps) {
  return (
    <header className="bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-md">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-3">
          <span className="text-3xl" aria-hidden="true">
            📋
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">BidWright</h1>
            <p className="text-sm text-indigo-100">
              An RFP compliance &amp; proposal-drafting agent for small contractors and business owners.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <StatusPill status={status} statusError={statusError} />
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label="Toggle color theme"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-lg transition hover:bg-white/25"
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </div>
    </header>
  );
}

function StatusPill({ status, statusError }: { status: StatusResponse | null; statusError: boolean }) {
  if (statusError) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium">
        <span className="h-2 w-2 rounded-full bg-red-400" />
        Could not reach the BidWright API
      </span>
    );
  }
  if (!status) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium">
        <span className="h-2 w-2 animate-pulse rounded-full bg-slate-300" />
        Checking model status&hellip;
      </span>
    );
  }
  return (
    <span
      title={status.status_text}
      className="inline-flex max-w-xs items-center gap-2 rounded-full bg-white/15 px-3 py-1.5 text-xs font-medium"
    >
      <span className={`h-2 w-2 flex-shrink-0 rounded-full ${status.ready ? "bg-emerald-400" : "bg-red-400"}`} />
      <span className="truncate">{status.status_text}</span>
    </span>
  );
}
