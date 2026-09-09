import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { fetchRunFile, runFileDownloadUrl } from '../api'
import type { RunFile } from '../types'

// Fixed tab order/labels - mirrors app_claimclarity.py's tabs exactly,
// independent of which files the run actually produced (a tab for a file
// that wasn't generated still appears, showing "Not generated" - same as
// the Streamlit demo's `_read()` fallback).
const FILE_TABS: { name: string; label: string }[] = [
  { name: 'decisions_needed.md', label: 'Decisions Needed' },
  { name: 'claim_summary.md', label: 'Claim Summary' },
  { name: 'denial_findings.md', label: 'Denial Findings' },
  { name: 'denial_cross_check.md', label: 'Independent Audit' },
  { name: 'appeal_package.md', label: 'Appeal Package' },
  { name: 'escalation_package.md', label: 'External Review & Escalation' },
]

const UNVERIFIED_LABEL = "Agent's Own Summary (unverified)"

interface Props {
  jobId: string
  files: RunFile[]
  summaryText: string
}

export default function ResultsTabs({ jobId, files, summaryText }: Props) {
  const tabs = [...FILE_TABS.map((t) => t.label), UNVERIFIED_LABEL]
  const [active, setActive] = useState(0)

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-200 p-2 dark:border-slate-800">
        {tabs.map((label, i) => (
          <button
            key={label}
            role="tab"
            aria-selected={active === i}
            onClick={() => setActive(i)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              active === i
                ? 'bg-teal-600 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="p-5">
        {active < FILE_TABS.length ? (
          <FileTab jobId={jobId} manifest={FILE_TABS[active]} entry={files.find((f) => f.name === FILE_TABS[active].name)} />
        ) : (
          <UnverifiedTab summaryText={summaryText} />
        )}
      </div>
    </section>
  )
}

function FileTab({
  jobId,
  manifest,
  entry,
}: {
  jobId: string
  manifest: { name: string; label: string }
  entry: RunFile | undefined
}) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setContent(null)
    setError(null)
    if (!entry) return
    let cancelled = false
    fetchRunFile(jobId, manifest.name)
      .then((text) => {
        if (!cancelled) setContent(text)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [jobId, manifest.name, entry])

  if (!entry) {
    return <p className="italic text-slate-500 dark:text-slate-400">Not generated.</p>
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2">
        <a
          href={runFileDownloadUrl(jobId, manifest.name)}
          download={manifest.name}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          ⬇ Download {manifest.name}
        </a>
        {entry.download && (
          <a
            href={runFileDownloadUrl(jobId, entry.download.name)}
            download={entry.download.name}
            className="rounded-lg border border-teal-300 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-800 transition hover:bg-teal-100 dark:border-teal-800 dark:bg-teal-950/50 dark:text-teal-300 dark:hover:bg-teal-900/50"
          >
            📅 {entry.download.label}
          </a>
        )}
      </div>
      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400">Failed to load: {error}</p>
      ) : content === null ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
      ) : (
        <div className="markdown">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

function UnverifiedTab({ summaryText }: { summaryText: string }) {
  return (
    <div>
      <p className="mb-4 rounded-lg bg-slate-100 p-3 text-xs italic text-slate-600 dark:bg-slate-800 dark:text-slate-400">
        This is the orchestrator&apos;s own free-text reply, shown for transparency. It can occasionally
        misstate specifics even when every generated file above is correct - treat{' '}
        <strong>Decisions Needed</strong> and the generated files as the source of truth, not this tab.
      </p>
      <div className="markdown">
        <ReactMarkdown>{summaryText}</ReactMarkdown>
      </div>
    </div>
  )
}
