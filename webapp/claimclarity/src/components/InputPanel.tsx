import { useRef, useState } from 'react'

interface Props {
  running: boolean
  onRun: (useExample: boolean, files: File[]) => void
}

export default function InputPanel({ running, onRun }: Props) {
  const [source, setSource] = useState<'example' | 'upload'>('example')
  const [files, setFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canRun = source === 'example' || files.length > 0

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Claim documents
      </h2>

      <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <SourceOption
          label="Use example (Maria Chen / Heartland Mutual)"
          selected={source === 'example'}
          onSelect={() => setSource('example')}
          disabled={running}
        />
        <SourceOption
          label="Upload files"
          selected={source === 'upload'}
          onSelect={() => setSource('upload')}
          disabled={running}
        />
      </div>

      {source === 'upload' && (
        <div className="mb-4">
          <label
            htmlFor="claim-file-upload"
            className="block cursor-pointer rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-4 text-center text-sm text-slate-600 transition hover:border-teal-400 hover:bg-teal-50/50 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300 dark:hover:border-teal-500"
          >
            <input
              id="claim-file-upload"
              ref={fileInputRef}
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx"
              disabled={running}
              className="hidden"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            {files.length > 0 ? (
              <ul className="mx-auto max-w-xs space-y-1 text-left">
                {files.map((f) => (
                  <li key={f.name} className="truncate font-mono text-xs text-slate-700 dark:text-slate-200">
                    📄 {f.name}
                  </li>
                ))}
              </ul>
            ) : (
              <span>
                Denial notice/EOB (required), and optionally a plan summary of benefits and/or medical
                record excerpt.
                <br />
                <span className="text-teal-700 dark:text-teal-400">Click to choose files</span>
              </span>
            )}
          </label>
        </div>
      )}

      <button
        type="button"
        disabled={running || !canRun}
        onClick={() => onRun(source === 'example', files)}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-teal-600 to-emerald-600 px-4 py-2.5 font-semibold text-white shadow transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:brightness-100"
      >
        {running ? (
          <>
            <Spinner /> Running…
          </>
        ) : (
          'Run ClaimClarity'
        )}
      </button>
      {!canRun && source === 'upload' && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Choose at least the denial notice/EOB to run.
        </p>
      )}
    </section>
  )
}

function SourceOption({
  label,
  selected,
  onSelect,
  disabled,
}: {
  label: string
  selected: boolean
  onSelect: () => void
  disabled: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={`rounded-lg border px-3 py-2.5 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-60 ${
        selected
          ? 'border-teal-500 bg-teal-50 font-medium text-teal-800 ring-1 ring-teal-500 dark:border-teal-500 dark:bg-teal-950/50 dark:text-teal-300'
          : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
      }`}
    >
      {label}
    </button>
  )
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}
