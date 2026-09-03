import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../api";
import { fetchChatHistory, sendChatMessage } from "../api";

interface ChatPanelProps {
  jobId: string;
}

export function ChatPanel({ jobId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchChatHistory(jobId)
      .then(({ messages }) => {
        if (!cancelled) setMessages(messages);
      })
      .catch(() => {
        // No prior history is fine; leave the panel empty.
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const { reply } = await sendChatMessage(jobId, text);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 px-5 py-3 dark:border-slate-800">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-50">Ask about this bid</h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Answers are grounded only in this run's own generated files.
        </p>
      </div>

      <div ref={logRef} className="max-h-80 space-y-3 overflow-y-auto p-5">
        {messages.length === 0 ? (
          <p className="text-sm text-slate-400">
            No questions yet. Try asking, for example, "what's the submission deadline?"
          </p>
        ) : (
          messages.map((m, i) => <ChatBubble key={i} message={m} />)
        )}
        {sending && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Spinner />
            Thinking&hellip;
          </div>
        )}
      </div>

      {error && (
        <p className="mx-5 mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="flex items-end gap-2 border-t border-slate-200 p-4 dark:border-slate-800">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Ask a question about this bid&hellip;"
          disabled={sending}
          className="flex-1 resize-none rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
          isUser
            ? "bg-indigo-600 text-white"
            : "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <span
      className="h-3.5 w-3.5 flex-shrink-0 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600 dark:border-slate-700 dark:border-t-indigo-400"
      aria-hidden="true"
    />
  );
}
