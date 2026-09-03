import { useEffect, useRef, useState } from 'react'
import { fetchChatHistory, sendChatMessage } from '../api'
import type { ChatMessage } from '../types'

interface Props {
  jobId: string
}

export default function ChatPanel({ jobId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    fetchChatHistory(jobId)
      .then((body) => {
        if (!cancelled) setMessages(body.messages)
      })
      .catch(() => {
        // A fresh job with no chat history yet is not an error condition.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [jobId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      // Remove the optimistically-added user message's dangling state by
      // leaving it visible but surfacing the error below - retrying just
      // re-sends the same text the user typed.
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 px-5 py-4 dark:border-slate-800">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          💬 Ask about this case
        </h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Answers are grounded only in this run&apos;s own generated files, and this isn&apos;t legal or
          medical advice.
        </p>
      </div>

      <div className="p-5">
        <div className="mb-3 max-h-72 space-y-3 overflow-y-auto rounded-lg bg-slate-50 p-3 dark:bg-slate-950/40">
          {!loaded ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
          ) : messages.length === 0 ? (
            <p className="text-sm italic text-slate-500 dark:text-slate-400">
              No questions yet. Try &ldquo;What&apos;s the appeal deadline?&rdquo; or &ldquo;Why was this
              denied?&rdquo;
            </p>
          ) : (
            messages.map((m, i) => <ChatBubble key={i} message={m} />)
          )}
          <div ref={bottomRef} />
        </div>

        {error && <p className="mb-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

        <form
          onSubmit={(e) => {
            e.preventDefault()
            handleSend()
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
            placeholder="Ask a question about this case…"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="rounded-lg bg-gradient-to-r from-teal-600 to-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:brightness-100"
          >
            {sending ? '…' : 'Send'}
          </button>
        </form>
      </div>
    </section>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-teal-600 text-white'
            : 'bg-white text-slate-800 shadow-sm dark:bg-slate-800 dark:text-slate-100'
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}
