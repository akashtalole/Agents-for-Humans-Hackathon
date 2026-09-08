import { useState } from 'react'
import type { RumorResponse } from '../types'
import { triageRumor } from '../api'
import { Card, Label, PrimaryButton, Prose, RiskBadge, SectionTitle, inputClass } from './ui'

const SAMPLES = [
  {
    label: 'Stampede rumor (Hindi)',
    text: 'Log keh rahe hain ki Ramkund pe bhagdad mach gayi hai, bahut log dab gaye',
    location: 'Ramkund approach, Panchavati',
  },
  {
    label: 'Ghat-closing rumor',
    text: 'Someone is telling everyone the ghat closes in 10 minutes and this is the last chance to bathe',
    location: 'Kushavarta Ghat, Trimbakeshwar',
  },
  {
    label: 'Bridge collapse rumor',
    text: 'People are saying a footbridge over the Godavari has cracked and is about to fall',
    location: 'Panchavati Godavari corridor',
  },
]

export default function RumorView() {
  const [text, setText] = useState('')
  const [location, setLocation] = useState('')
  const [spreadingFast, setSpreadingFast] = useState(true)
  const [result, setResult] = useState<RumorResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(overrideText?: string, overrideLocation?: string) {
    const t = (overrideText ?? text).trim()
    const l = (overrideLocation ?? location).trim()
    if (!t || !l) {
      setError('Both the rumor text and a location are required.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      setResult(await triageRumor(t, l, spreadingFast))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <SectionTitle eyebrow="Kumbh Rakshak" title="Rumor Desk" hindi="अफवाह · the crush trigger that isn't a barricade" />
      <p className="mb-6 max-w-4xl text-sm text-slate-400">
        A rumor moving through a dense crowd is a crowd-safety event. In 2025,{' '}
        <strong className="text-slate-200">18 people died at New Delhi railway station</strong> when a fainting incident spawned
        "rumours of a stampede-like situation" among Kumbh travellers. The counter-message is a safety intervention — and it
        carries its own lethal failure mode, which is why every draft below is scanned by a deterministic guardrail before a
        human ever sees it as broadcast-ready.
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-white">Report a rumor</h2>
          <div className="mb-4 space-y-1.5">
            {SAMPLES.map((s) => (
              <button
                key={s.label}
                onClick={() => {
                  setText(s.text)
                  setLocation(s.location)
                  run(s.text, s.location)
                }}
                className="w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-left text-xs text-slate-400 transition hover:border-saffron-400/40 hover:text-saffron-200"
              >
                <div className="font-semibold">{s.label}</div>
                <div className="mt-0.5 line-clamp-2 opacity-70">{s.text}</div>
              </button>
            ))}
          </div>

          <Label>What is being said in the crowd</Label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder="As reported by field staff…"
            className={`${inputClass} mb-3 resize-y`}
          />
          <Label>Location</Label>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className={`${inputClass} mb-3`} />
          <label className="mb-4 flex items-center gap-2 text-xs text-slate-400">
            <input
              type="checkbox"
              checked={spreadingFast}
              onChange={(e) => setSpreadingFast(e.target.checked)}
              className="accent-saffron-500"
            />
            Field staff report it is spreading fast
          </label>
          <PrimaryButton onClick={() => run()} disabled={loading} className="w-full">
            {loading ? 'Assessing…' : 'Assess & draft counter-message'}
          </PrimaryButton>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </Card>

        <Card className="lg:col-span-3">
          {!result && <p className="text-sm text-slate-500">Report a rumor to see its assessment and a draft counter-message.</p>}
          {result && (
            <div className="trinetra-fade-in space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-white">{result.assessment.category}</div>
                  <div className="text-xs text-slate-500">crush risk assessment</div>
                </div>
                <RiskBadge level={result.assessment.crush_risk} />
              </div>

              <Prose className="text-sm text-slate-300">{result.assessment.why_dangerous}</Prose>

              <div className="rounded-xl border border-amber-400/30 bg-amber-500/5 p-3">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-300">
                  ⚠️ Verify before broadcasting anything
                </h3>
                <ul className="space-y-1 text-xs text-slate-300">
                  {result.assessment.verify_before_broadcast.map((v, i) => (
                    <li key={i}>• {v}</li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Draft counter-message — NOT approved for broadcast
                </h3>
                <div className="space-y-2">
                  <blockquote className="rounded-lg border-l-2 border-saffron-400/60 bg-white/[0.03] px-3 py-2 text-sm text-slate-100">
                    {result.assessment.counter_message}
                  </blockquote>
                  <blockquote className="rounded-lg border-l-2 border-saffron-400/30 bg-white/[0.03] px-3 py-2 text-sm text-slate-300">
                    {result.assessment.counter_message_local}
                  </blockquote>
                </div>
                <div className="mt-2 text-xs text-slate-500">
                  Channels: {result.assessment.recommended_channels.join(', ')}
                </div>
              </div>

              <div
                className={`rounded-xl border p-3 ${
                  result.guardrail.passed ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/40 bg-red-500/10'
                }`}
              >
                <h3
                  className={`mb-1 text-xs font-semibold uppercase tracking-wide ${
                    result.guardrail.passed ? 'text-emerald-300' : 'text-red-300'
                  }`}
                >
                  {result.guardrail.passed ? '✅ Guardrail passed' : '❌ Guardrail BLOCKED this draft'}
                </h3>
                <p className="text-xs text-slate-400">{result.guardrail.summary}</p>
                {result.guardrail.findings.map((f, i) => (
                  <div key={i} className="mt-2 rounded-lg bg-black/20 p-2 text-xs">
                    <div className="font-semibold text-red-300">{f.rule}</div>
                    <div className="italic text-slate-400">"{f.excerpt}"</div>
                    <div className="text-slate-500">{f.explanation}</div>
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-slate-600">
                Trinetra never broadcasts. A human official verifies the points above and issues the message.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
