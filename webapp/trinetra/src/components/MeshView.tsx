import { useEffect, useState } from 'react'
import type { PeerAgent, PeerConsultation, PeerResponse, TrustLevel } from '../types'
import { consultPeers, fetchPeers } from '../api'
import { Card, Label, PrimaryButton, SectionTitle, inputClass } from './ui'

const TRUST_STYLE: Record<TrustLevel, string> = {
  verified_authority: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  known_partner: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  unverified: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
}

const TRUST_LABEL: Record<TrustLevel, string> = {
  verified_authority: 'verified authority',
  known_partner: 'known partner',
  unverified: 'unverified',
}

const SAMPLE_QUESTIONS = [
  'What is the planned Gangapur Dam release over the next two hours?',
  'How many casualty beds are free right now?',
  'Are any trains arriving early at Nashik Road?',
]

function TrustChip({ trust }: { trust: TrustLevel }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${TRUST_STYLE[trust]}`}>
      {TRUST_LABEL[trust]}
    </span>
  )
}

function ResponseCard({ r }: { r: PeerResponse }) {
  const withheld = !r.error && r.scan && !r.scan.safe_to_surface
  const border = r.error
    ? 'border-white/10 bg-white/[0.02]'
    : withheld
      ? 'border-red-500/40 bg-red-500/[0.06]'
      : 'border-emerald-500/25 bg-emerald-500/[0.04]'

  return (
    <div className={`rounded-xl border p-4 ${border}`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-100">{r.peer_name}</span>
        <TrustChip trust={r.trust} />
        <span className="text-[10px] uppercase tracking-wide text-slate-600">
          {r.error ? 'unreachable' : withheld ? '⛔ withheld by trust scan' : '✅ answered'}
        </span>
      </div>
      <div className="mb-2 text-[11px] text-slate-500">{r.operator}</div>

      {r.error ? (
        <p className="text-xs italic text-slate-500">{r.error}</p>
      ) : (
        <blockquote className="mb-2 rounded-lg border-l-2 border-white/15 bg-black/20 px-3 py-2 text-xs text-slate-300">
          {r.text || '(empty reply)'}
        </blockquote>
      )}

      {r.scan && (
        <>
          <p className="text-[11px] text-slate-500">{r.scan.summary}</p>
          {r.scan.findings.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {r.scan.findings.map((f, i) => (
                <div key={i} className="rounded-lg bg-black/25 p-2 text-[11px]">
                  <div className="font-semibold text-red-300">{f.rule}</div>
                  <div className="italic text-slate-500">"{f.excerpt}"</div>
                  <div className="text-slate-500">{f.explanation}</div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function MeshView() {
  const [peers, setPeers] = useState<PeerAgent[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [question, setQuestion] = useState(SAMPLE_QUESTIONS[0])
  const [result, setResult] = useState<PeerConsultation | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchPeers()
      .then((r) => {
        setPeers(r.peers)
        setSelected(r.peers.map((p) => p.peer_id))
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  }

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(await consultPeers(question, selected))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <SectionTitle eyebrow="Agent2Agent" title="Agent Mesh" hindi="अन्तर-संस्था · talking to agents we do not own" />
      <p className="mb-6 max-w-4xl text-sm text-slate-400">
        At a Kumbh the agencies are genuinely separate — Central Railway, the municipal hospitals, the irrigation
        department that operates Gangapur Dam. Each holds something Trinetra cannot compute. A2A is how that connection is
        made, and the design problem it creates is that{' '}
        <strong className="text-slate-200">a peer agent's output is untrusted input</strong>. Registration is an{' '}
        <strong className="text-slate-200">allowlist</strong>, every reply is scanned by deterministic code before it is
        shown as decision-support, and nothing arriving here ever becomes a number Trinetra plans with.
      </p>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-white">Registered peers</h2>
          <p className="mb-3 text-[11px] text-slate-500">
            Trinetra will not call a URL that is not on this list. These entries are illustrative — the real agencies
            would operate these endpoints themselves.
          </p>

          <div className="mb-4 space-y-2">
            {peers.map((p) => (
              <label
                key={p.peer_id}
                className={`flex cursor-pointer items-start gap-2 rounded-lg border p-3 transition ${
                  selected.includes(p.peer_id)
                    ? 'border-saffron-400/40 bg-saffron-500/[0.06]'
                    : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(p.peer_id)}
                  onChange={() => toggle(p.peer_id)}
                  className="mt-0.5 accent-saffron-500"
                />
                <span className="min-w-0 flex-1">
                  <span className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold text-slate-100">{p.name}</span>
                    <TrustChip trust={p.trust} />
                  </span>
                  <span className="block text-[11px] text-slate-500">{p.operator}</span>
                  <span className="mt-1 block text-[10px] text-slate-600">{p.capabilities.join(' · ')}</span>
                  {p.note && <span className="mt-1 block text-[10px] leading-relaxed text-slate-600">{p.note}</span>}
                </span>
              </label>
            ))}
          </div>

          <Label>Question</Label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            className={`${inputClass} mb-2 resize-y`}
          />
          <div className="mb-3 space-y-1">
            {SAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => setQuestion(q)}
                className="block w-full rounded-lg border border-white/10 bg-white/[0.02] px-2 py-1.5 text-left text-[11px] text-slate-500 transition hover:border-saffron-400/40 hover:text-saffron-200"
              >
                {q}
              </button>
            ))}
          </div>

          <PrimaryButton onClick={run} disabled={loading || selected.length === 0} className="w-full">
            {loading ? 'Consulting peers…' : `Consult ${selected.length} peer${selected.length === 1 ? '' : 's'}`}
          </PrimaryButton>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </Card>

        <div className="xl:col-span-3">
          <Card>
            <h2 className="mb-1 text-sm font-semibold text-white">What the peers said</h2>
            <p className="mb-4 text-[11px] leading-relaxed text-amber-300/80">
              Everything below is a third party's assertion, not a Trinetra finding. No figure here enters Trinetra's
              deterministic risk calculations — if an operator wants to plan on one of these numbers, they enter it
              themselves, having decided to believe it.
            </p>

            {!result && (
              <p className="text-sm text-slate-500">
                In this build the peer endpoints are placeholders, so expect unreachable replies unless you are running a
                peer locally. That path is worth seeing too: a peer being down must never take Trinetra with it.
              </p>
            )}

            {result && (
              <div className="trinetra-fade-in space-y-3">
                <p className="text-[11px] text-slate-500">{result.summary}</p>
                {result.responses.map((r) => (
                  <ResponseCard key={r.peer_id} r={r} />
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
