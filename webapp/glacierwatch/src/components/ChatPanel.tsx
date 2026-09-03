import { useEffect, useRef, useState } from 'react'
import { fetchChatHistory, sendChatMessage } from '../api'
import type { ChatMessage } from '../types'

/** Conversational follow-up, grounded ONLY in this run's own generated
 * files (glacierwatch/api.py's /chat, glacierwatch.tools.guardrail's
 * sibling discipline applied to Q&A instead of drafting) - never a
 * prediction, even when asked directly. Shown once a run has finished
 * (awaiting_approval or completed) since there are documents to ground on. */
export default function ChatPanel({ jobId }: { jobId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchChatHistory(jobId)
      .then((data) => {
        if (!cancelled) setMessages(data.messages)
      })
      .catch(() => {
        /* start with an empty history if this fails */
      })
    return () => {
      cancelled = true
    }
  }, [jobId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const message = input.trim()
    if (!message || sending) return
    setSending(true)
    setError(null)
    setMessages((prev) => [...prev, { role: 'user', content: message }])
    setInput('')
    try {
      const { reply } = await sendChatMessage(jobId, message)
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }])
    } catch {
      setError('Could not reach the chat endpoint - try again.')
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <div className="border-b border-slate-200 px-5 py-3 dark:border-slate-700">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          Ask about this week&apos;s watchlist
        </h2>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          Answers are grounded only in this run&apos;s own generated files, and will never predict if or
          when a hazard will occur.
        </p>
      </div>

      <div className="max-h-80 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400 dark:text-slate-500">
            No questions yet - try &quot;how many sites are being tracked?&quot;
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                m.role === 'user'
                  ? 'bg-sky-600 text-white'
                  : 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {sending && <p className="text-xs text-slate-400 dark:text-slate-500">Thinking…</p>}
        <div ref={endRef} />
      </div>

      {error && <p className="px-5 pb-2 text-xs text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-700">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="Ask a question about this run…"
          disabled={sending}
          className="flex-1 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </section>
  )
}
