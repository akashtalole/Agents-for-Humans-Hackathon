import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { PilgrimGuidance } from '../types'
import { askPilgrim } from '../api'
import { Card, inputClass, PrimaryButton, SectionTitle } from './ui'

const LANGUAGES = [
  { value: 'hindi', label: 'हिन्दी Hindi' },
  { value: 'marathi', label: 'मराठी Marathi' },
  { value: 'english', label: 'English' },
  { value: 'gujarati', label: 'ગુજરાતી Gujarati' },
  { value: 'bhojpuri', label: 'भोजपुरी Bhojpuri' },
  { value: 'tamil', label: 'தமிழ் Tamil' },
  { value: 'telugu', label: 'తెలుగు Telugu' },
  { value: 'kannada', label: 'ಕನ್ನಡ Kannada' },
  { value: 'bengali', label: 'বাংলা Bengali' },
]

const SAMPLE_QUERIES = [
  { text: 'Ramkund par kitni bheed hai abhi?', language: 'hindi' },
  { text: "I can't move, the crowd is crushing me near Ramkund, help!", language: 'english' },
  { text: 'Kushavarta ghat kaise pahunche Trimbakeshwar se?', language: 'hindi' },
]

interface Turn {
  question: string
  language: string
  guidance: PilgrimGuidance | null
  error: string | null
}

export default function PilgrimView() {
  const [text, setText] = useState('')
  const [language, setLanguage] = useState('hindi')
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)

  async function submit(overrideText?: string, overrideLanguage?: string) {
    const q = (overrideText ?? text).trim()
    const lang = overrideLanguage ?? language
    if (!q || loading) return
    setLoading(true)
    setText('')
    const turn: Turn = { question: q, language: lang, guidance: null, error: null }
    setTurns((t) => [...t, turn])
    try {
      const guidance = await askPilgrim(q, lang)
      setTurns((t) => t.map((x) => (x === turn ? { ...x, guidance } : x)))
    } catch (err) {
      setTurns((t) => t.map((x) => (x === turn ? { ...x, error: err instanceof Error ? err.message : String(err) } : x)))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <SectionTitle eyebrow="Pillar I" title="Yatri Netra" hindi="यात्री नेत्र · pilgrim assistant" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="mb-4 flex flex-wrap gap-2">
            {SAMPLE_QUERIES.map((s) => (
              <button
                key={s.text}
                onClick={() => submit(s.text, s.language)}
                className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition hover:border-saffron-400/40 hover:text-saffron-200"
              >
                {s.text}
              </button>
            ))}
          </div>

          <div className="trinetra-scrollbar mb-4 max-h-[28rem] min-h-[10rem] space-y-4 overflow-y-auto pr-1">
            {turns.length === 0 && (
              <div className="flex h-32 items-center justify-center text-sm text-slate-600">
                Ask a question in any supported language — try one of the samples above.
              </div>
            )}
            {turns.map((t, i) => (
              <div key={i} className="trinetra-fade-in space-y-2">
                <div className="ml-auto max-w-[85%] rounded-2xl rounded-tr-sm bg-saffron-600/20 px-4 py-2 text-sm text-saffron-100">
                  {t.question}
                </div>
                {t.error && (
                  <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
                    {t.error}
                  </div>
                )}
                {t.guidance && (
                  <div className="max-w-[85%] space-y-2 rounded-2xl rounded-tl-sm border border-white/10 bg-white/5 px-4 py-3 text-sm">
                    <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 text-slate-100">
                      <ReactMarkdown>{t.guidance.answer}</ReactMarkdown>
                    </div>
                    {t.guidance.suggested_route && (
                      <div className="text-xs text-slate-400">
                        <span className="font-semibold text-slate-300">Route:</span> {t.guidance.suggested_route}
                      </div>
                    )}
                    {t.guidance.ghat_crowd_advisory && (
                      <div className="text-xs text-slate-400">
                        <span className="font-semibold text-slate-300">Crowd status:</span> {t.guidance.ghat_crowd_advisory}
                      </div>
                    )}
                    {t.guidance.safety_note && (
                      <div className="text-xs text-amber-300">
                        <span className="font-semibold">Safety note:</span> {t.guidance.safety_note}
                      </div>
                    )}
                    {t.guidance.escalate_to_sos && (
                      <div className="flex items-center gap-1.5 rounded-lg border border-red-500/40 bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-300">
                        ⚠️ Escalated as a possible emergency — routed for Kumbh Rakshak follow-up
                      </div>
                    )}
                  </div>
                )}
                {!t.guidance && !t.error && (
                  <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-500">
                    <span className="inline-flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500 [animation-delay:-0.3s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500 [animation-delay:-0.15s]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500" />
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              submit()
            }}
            className="flex gap-2"
          >
            <select value={language} onChange={(e) => setLanguage(e.target.value)} className={`${inputClass} w-40 shrink-0`}>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value} className="bg-[#0b0f1a]">
                  {l.label}
                </option>
              ))}
            </select>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask Yatri Sahayak anything about the Kumbh…"
              className={inputClass}
            />
            <PrimaryButton type="submit" disabled={loading || !text.trim()}>
              {loading ? '…' : 'Ask'}
            </PrimaryButton>
          </form>
        </Card>

        <Card>
          <h2 className="mb-2 text-sm font-semibold text-white">About Yatri Sahayak</h2>
          <ul className="space-y-2 text-sm text-slate-400">
            <li>• Answers only from bundled, cited site data — never invents a ghat, distance, or crowd status.</li>
            <li>• Actively watches for emergencies hidden inside an ordinary-sounding question.</li>
            <li>• Every response can be reformatted for SMS/USSD-only phones — see Prashasan Netra's network note.</li>
          </ul>
        </Card>
      </div>
    </div>
  )
}
