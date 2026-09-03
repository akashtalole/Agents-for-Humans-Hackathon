import ReactMarkdown from 'react-markdown'

/** Always visible, unconditionally - matches app_glacierwatch.py's
 * `st.warning(DISCLAIMER)`, which renders regardless of run state. The text
 * itself is fetched from GET /api/status (glacierwatch.rendering.DISCLAIMER)
 * rather than hardcoded here, so it can never drift from the source of
 * truth - see GLACIERWATCH.md's non-prediction framing. */
export default function DisclaimerBanner({ text }: { text: string | null }) {
  return (
    <div
      role="alert"
      className="border-b border-amber-300 bg-amber-100 px-4 py-3 text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/60 dark:text-amber-100"
    >
      <div className="mx-auto flex max-w-5xl items-start gap-2 sm:px-2">
        <span aria-hidden="true" className="mt-0.5 text-lg leading-none">
          ⚠️
        </span>
        <div className="prose prose-sm max-w-none text-amber-950 [&_p]:m-0 dark:prose-invert dark:text-amber-100">
          {text ? <ReactMarkdown>{text}</ReactMarkdown> : <p>Loading disclaimer…</p>}
        </div>
      </div>
    </div>
  )
}
