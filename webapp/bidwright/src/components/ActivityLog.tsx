import { useEffect, useRef, useState } from "react";
import { runEventsUrl } from "../api";

interface ActivityLogProps {
  jobId: string;
  onDone: () => void;
}

export function ActivityLog({ jobId, onDone }: ActivityLogProps) {
  const [lines, setLines] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    setLines([]);
    const source = new EventSource(runEventsUrl(jobId));

    source.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.done) {
          source.close();
          onDoneRef.current();
          return;
        }
        if (data.tool) {
          setLines((prev) => [...prev, `🔧 calling \`${data.tool}\``]);
        }
      } catch {
        // ignore malformed events
      }
    };

    source.onerror = () => {
      // The stream ends (connection closed by the server) once "done" is
      // sent; a late/duplicate error after that is expected and harmless.
      source.close();
    };

    return () => source.close();
  }, [jobId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex items-center gap-3">
        <Spinner />
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-50">
          BidWright is analyzing the RFP, checking compliance, and drafting the proposal&hellip;
        </h2>
      </div>
      <div
        ref={logRef}
        className="h-64 overflow-y-auto rounded-lg bg-slate-950 p-3 font-mono text-xs text-emerald-300 shadow-inner"
      >
        {lines.length === 0 ? (
          <p className="text-slate-500">Waiting for the agent to start&hellip;</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap py-0.5">
              {line}
            </div>
          ))
        )}
        <span className="log-cursor text-emerald-400">▍</span>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <span
      className="h-5 w-5 flex-shrink-0 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600 dark:border-slate-700 dark:border-t-indigo-400"
      aria-hidden="true"
    />
  );
}
