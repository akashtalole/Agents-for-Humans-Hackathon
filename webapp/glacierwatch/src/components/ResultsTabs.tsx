import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { fetchFile } from '../api'
import type { FileEntry, Site } from '../types'

const TABS = [
  'Weekly Watchlist',
  'Independent Audit',
  'Site Profiles',
  'Current Conditions',
  "Agent's Own Summary (unverified)",
] as const
type Tab = (typeof TABS)[number]

function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-slate max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-sky-600 dark:prose-a:text-sky-400">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function WeeklyWatchlistTab({ jobId }: { jobId: string }) {
  const [content, setContent] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchFile(jobId, 'watchlist_report.md').then((text) => {
      if (!cancelled) setContent(text)
    })
    return () => {
      cancelled = true
    }
  }, [jobId])

  if (content === null) return <p className="text-sm text-slate-500">Loading…</p>

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={() => downloadText('watchlist_report.md', content)}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          ⬇️ Download watchlist_report.md
        </button>
      </div>
      <Markdown content={content} />
    </div>
  )
}

function IndependentAuditTab({ jobId }: { jobId: string }) {
  const [content, setContent] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchFile(jobId, 'risk_cross_check.md').then((text) => {
      if (!cancelled) setContent(text)
    })
    return () => {
      cancelled = true
    }
  }, [jobId])

  if (content === null) return <p className="text-sm text-slate-500">Loading…</p>

  return (
    <div>
      <p className="mb-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400">
        A second, independent agent re-derives each active site's priority level from scratch, with no
        view of the first assessment. When the two disagree, the <strong>more cautious</strong> rating is
        always adopted here - understating risk is worse than overstating it.
      </p>
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={() => downloadText('risk_cross_check.md', content)}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
        >
          ⬇️ Download risk_cross_check.md
        </button>
      </div>
      <Markdown content={content} />
    </div>
  )
}

function SiteProfilesTab({ jobId, sites }: { jobId: string; sites: Site[] }) {
  const [contents, setContents] = useState<Record<string, string> | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all(sites.map((s) => fetchFile(jobId, `site_profile_${s.id}.md`))).then((texts) => {
      if (cancelled) return
      const map: Record<string, string> = {}
      sites.forEach((s, i) => {
        map[s.id] = texts[i]
      })
      setContents(map)
    })
    return () => {
      cancelled = true
    }
  }, [jobId, sites])

  if (contents === null) return <p className="text-sm text-slate-500">Loading…</p>

  return (
    <div>
      {sites.map((site, i) => (
        <div key={site.id}>
          <Markdown content={contents[site.id]} />
          {i < sites.length - 1 && <hr className="my-6 border-slate-200 dark:border-slate-700" />}
        </div>
      ))}
    </div>
  )
}

function CurrentConditionsTab({ jobId, sites }: { jobId: string; sites: Site[] }) {
  const activeSites = sites.filter((s) => s.status === 'active_watch')
  const [contents, setContents] = useState<Record<string, string> | null>(null)

  useEffect(() => {
    let cancelled = false
    if (activeSites.length === 0) {
      setContents({})
      return
    }
    Promise.all(activeSites.map((s) => fetchFile(jobId, `site_conditions_${s.id}.md`))).then((texts) => {
      if (cancelled) return
      const map: Record<string, string> = {}
      activeSites.forEach((s, i) => {
        map[s.id] = texts[i]
      })
      setContents(map)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, sites])

  if (activeSites.length === 0) {
    return <p className="text-sm text-slate-600 dark:text-slate-400">No active_watch sites in this run.</p>
  }
  if (contents === null) return <p className="text-sm text-slate-500">Loading…</p>

  return (
    <div>
      {activeSites.map((site, i) => (
        <div key={site.id}>
          <h3 className="mb-2 text-lg font-semibold text-slate-900 dark:text-slate-100">{site.name}</h3>
          <Markdown content={contents[site.id]} />
          {i < activeSites.length - 1 && <hr className="my-6 border-slate-200 dark:border-slate-700" />}
        </div>
      ))}
    </div>
  )
}

function AgentSummaryTab({ summaryText }: { summaryText: string }) {
  return (
    <div>
      <p className="mb-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400">
        This is the orchestrator's own free-text reply, shown for transparency. It can occasionally
        misstate specifics even when every generated file above is correct - treat{' '}
        <strong>Weekly Watchlist</strong> as the source of truth, not this tab.
      </p>
      <Markdown content={summaryText} />
    </div>
  )
}

export default function ResultsTabs({
  jobId,
  sites,
  summaryText,
}: {
  jobId: string
  sites: Site[]
  files: FileEntry[]
  summaryText: string
}) {
  const [active, setActive] = useState<Tab>('Weekly Watchlist')

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-wrap gap-1 border-b border-slate-200 px-2 pt-2 dark:border-slate-700">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActive(tab)}
            className={`rounded-t-md px-3 py-2 text-sm font-medium transition ${
              active === tab
                ? 'border-b-2 border-sky-600 text-sky-700 dark:border-sky-400 dark:text-sky-300'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="p-5">
        {active === 'Weekly Watchlist' && <WeeklyWatchlistTab jobId={jobId} />}
        {active === 'Independent Audit' && <IndependentAuditTab jobId={jobId} />}
        {active === 'Site Profiles' && <SiteProfilesTab jobId={jobId} sites={sites} />}
        {active === 'Current Conditions' && <CurrentConditionsTab jobId={jobId} sites={sites} />}
        {active === "Agent's Own Summary (unverified)" && <AgentSummaryTab summaryText={summaryText} />}
      </div>
    </section>
  )
}
