import { useEffect, useState } from "react";
import { createRun, fetchRun, fetchStatus, type RunStatus, type StatusResponse } from "./api";
import { ActivityLog } from "./components/ActivityLog";
import { Header } from "./components/Header";
import { InputPanel } from "./components/InputPanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { useTheme } from "./useTheme";

type Phase = "idle" | "running" | "done";

function App() {
  const [theme, toggleTheme] = useTheme();
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [statusError, setStatusError] = useState(false);

  const [phase, setPhase] = useState<Phase>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    fetchStatus()
      .then(setStatus)
      .catch(() => setStatusError(true));
  }, []);

  async function handleRun(input: {
    useExample: boolean;
    rfp: File | null;
    profile: File | null;
    amendment: File | null;
  }) {
    setRunError(null);
    setRun(null);
    setPhase("running");
    try {
      const { job_id } = await createRun(input);
      setJobId(job_id);
    } catch (err) {
      setRunError(String(err instanceof Error ? err.message : err));
      setPhase("idle");
    }
  }

  async function pollUntilDone(id: string) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const result = await fetchRun(id);
      if (result.status !== "running") {
        setRun(result);
        setPhase("done");
        return;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    // Fall through: mark done with whatever we last saw so the UI doesn't hang forever.
    setPhase("done");
  }

  return (
    <div className="flex min-h-full flex-col">
      <Header status={status} statusError={statusError} theme={theme} onToggleTheme={toggleTheme} />

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
        <InputPanel running={phase === "running"} ready={status?.ready ?? true} onRun={handleRun} />

        {runError && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            Could not start the run: {runError}
          </p>
        )}

        {phase === "running" && jobId && <ActivityLog jobId={jobId} onDone={() => pollUntilDone(jobId)} />}

        {phase === "done" && jobId && run && <ResultsPanel jobId={jobId} run={run} />}

        {phase === "idle" && !runError && (
          <p className="rounded-xl border border-dashed border-slate-300 bg-white/60 px-5 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
            Configure an RFP and company profile above, then click <strong>Run BidWright</strong>.
          </p>
        )}
      </main>

      <footer className="mx-auto w-full max-w-6xl px-4 pb-6 text-center text-xs text-slate-400 sm:px-6 dark:text-slate-600">
        BidWright — built with the Strands Agents SDK for the Agents for Humans Hackathon.
      </footer>
    </div>
  );
}

export default App;
