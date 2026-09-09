import { useState } from 'react'
import type { CommandResponse, ResponderType, SitesResponse } from '../types'
import { runIncidentCommand } from '../api'
import { Card, Label, PrimaryButton, Prose, RiskBadge, SectionTitle, inputClass } from './ui'

// The board a Nashik control room can actually face at 04:00 on a Shahi Snan:
// a danger-stage release, ghats near capacity, live incidents and a rumour -
// all at once, competing for the same units.
const PRESET = {
  discharge: 22000,
  occupancy: { ramkund: 8000, panchavati_godavari: 4800, kalaram_marg: 1400, kushavarta: 3000 } as Record<string, number>,
  sos: [
    { description: 'elderly man collapsed in the crowd, not breathing well', location: 'Ramkund' },
    { description: 'child separated from family, crowd very dense', location: 'Kalaram Mandir Marg' },
  ],
  rumor: { text: 'Log keh rahe hain ki Ramkund pe bhagdad mach gayi hai', location: 'Ramkund approach' },
}

const RESPONDER_COLOR: Record<ResponderType, string> = {
  police: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
  medical: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  ambulance: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
  rescue: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
  announcer: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
}

function ResponderChip({ type }: { type: ResponderType }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${RESPONDER_COLOR[type]}`}>
      {type}
    </span>
  )
}

export default function CommandView({ sites }: { sites: SitesResponse }) {
  const [discharge, setDischarge] = useState<number>(PRESET.discharge)
  const [occupancy, setOccupancy] = useState<Record<string, number>>(
    Object.fromEntries(sites.ghats.map((g) => [g.id, PRESET.occupancy[g.id] ?? 0])),
  )
  const [includeSos, setIncludeSos] = useState(true)
  const [includeRumor, setIncludeRumor] = useState(true)
  const [redTeam, setRedTeam] = useState(true)
  const [result, setResult] = useState<CommandResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(
        await runIncidentCommand({
          discharge_cusecs: discharge || null,
          occupancy,
          sos: includeSos ? PRESET.sos : [],
          rumor: includeRumor ? PRESET.rumor : null,
          run_red_team: redTeam,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const shortfalls = result?.allocation.allocations.filter((a) => !a.fully_met) ?? []

  return (
    <div>
      <SectionTitle
        eyebrow="Sankat Nirnay"
        title="Incident Command"
        hindi="संकट निर्णय · when every desk wants the same units"
      />
      <p className="mb-6 max-w-4xl text-sm text-slate-400">
        Every other view answers one question about one hazard. A control room at 04:00 on a Shahi Snan morning faces all of
        them at once — and each desk, reasoning correctly in isolation, assumes it can have whatever it asks for. This view
        runs them together and then does the two things no single desk can:{' '}
        <strong className="text-slate-200">divide a finite responder pool</strong> in a documented, reproducible order, and{' '}
        <strong className="text-slate-200">find the directives that cannot both be executed</strong> — like a flood
        evacuation routed into the 1.8m lane where 39 people died in 2003.
      </p>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-white">The board</h2>

          <Label>Gangapur Dam discharge (cusecs) — 0 takes the river out of it</Label>
          <input
            type="number"
            value={discharge}
            onChange={(e) => setDischarge(Number(e.target.value))}
            className={`${inputClass} mb-4`}
          />

          <Label>Ghat occupancy</Label>
          <div className="mb-4 space-y-2">
            {sites.ghats.map((g) => (
              <div key={g.id} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-xs text-slate-400" title={g.name}>
                  {g.name}
                </span>
                <input
                  type="number"
                  value={occupancy[g.id] ?? 0}
                  onChange={(e) => setOccupancy((o) => ({ ...o, [g.id]: Number(e.target.value) }))}
                  className={inputClass.replace('w-full', 'w-24 shrink-0')}
                />
              </div>
            ))}
          </div>

          <div className="space-y-2 text-xs text-slate-400">
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={includeSos} onChange={(e) => setIncludeSos(e.target.checked)} className="mt-0.5 accent-saffron-500" />
              <span>
                Two open SOS incidents
                <span className="block text-slate-600">a collapsed elderly man at Ramkund, a child separated at Kalaram Marg</span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={includeRumor} onChange={(e) => setIncludeRumor(e.target.checked)} className="mt-0.5 accent-saffron-500" />
              <span>
                A stampede rumour spreading
                <span className="block text-slate-600">"Ramkund pe bhagdad mach gayi hai"</span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input type="checkbox" checked={redTeam} onChange={(e) => setRedTeam(e.target.checked)} className="mt-0.5 accent-saffron-500" />
              <span>
                Run the adversarial plan review
                <span className="block text-slate-600">a second agent that only looks for what breaks the plan</span>
              </span>
            </label>
          </div>

          <PrimaryButton onClick={run} disabled={loading} className="mt-4 w-full">
            {loading ? 'Reconciling every desk…' : 'Reconcile the board'}
          </PrimaryButton>
          {loading && (
            <p className="mt-2 text-[11px] text-slate-500">
              Each desk runs independently first, then the allocator and conflict scanner run over their combined output.
            </p>
          )}
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </Card>

        <div className="space-y-4 xl:col-span-3">
          {!result && (
            <Card>
              <p className="text-sm text-slate-500">Set the board and reconcile it to see one command picture.</p>
            </Card>
          )}

          {result && (
            <div className="trinetra-fade-in space-y-4">
              <Card>
                <div className="mb-2 flex items-start justify-between gap-3">
                  <h2 className="text-sm font-semibold text-white">{result.plan.headline}</h2>
                  <RiskBadge level={result.plan.overall_risk} />
                </div>
                <Prose className="text-xs text-slate-400">{result.plan.narrative_summary}</Prose>
              </Card>

              {/* Ordered deliberately: the calls needing a human come first. */}
              {result.plan.escalate_to_human.length > 0 && (
                <Card className="border-red-500/40 bg-red-500/[0.06]">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-300">
                    🔴 Calls the commander must make personally
                  </h3>
                  <ul className="space-y-2 text-xs text-slate-300">
                    {result.plan.escalate_to_human.map((e, i) => (
                      <li key={i}>• {e}</li>
                    ))}
                  </ul>
                </Card>
              )}

              {result.conflicts.conflicts.length > 0 && (
                <Card>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-300">Conflicting directives</h3>
                  <p className="mb-3 text-[11px] text-slate-500">{result.conflicts.summary}</p>
                  <div className="space-y-2">
                    {result.conflicts.conflicts.map((c, i) => (
                      <div key={i} className="rounded-lg border border-white/5 bg-black/20 p-3">
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <RiskBadge level={c.severity} />
                          <span className="text-xs font-semibold text-slate-200">{c.target_name}</span>
                          <span className="text-[10px] uppercase tracking-wide text-slate-600">
                            {c.kind.replace(/_/g, ' ')} · {c.sources.join(' + ')}
                          </span>
                        </div>
                        <p className="text-xs leading-relaxed text-slate-400">{c.detail}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {result.plan.accepted_risks.length > 0 && (
                <Card>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Accepted risks — what this plan knowingly gives up
                  </h3>
                  <ul className="space-y-1.5 text-xs text-slate-400">
                    {result.plan.accepted_risks.map((r, i) => (
                      <li key={i}>• {r}</li>
                    ))}
                  </ul>
                </Card>
              )}

              <Card>
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Execution sequence</h3>
                <div className="space-y-2">
                  {[...result.plan.decisions]
                    .sort((a, b) => a.sequence - b.sequence)
                    .map((d) => (
                      <div
                        key={d.sequence}
                        className={`rounded-lg border p-3 ${
                          d.contested ? 'border-amber-400/40 bg-amber-500/[0.06]' : 'border-white/5 bg-white/[0.02]'
                        }`}
                      >
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-saffron-500/20 text-[10px] font-bold text-saffron-300">
                            {d.sequence}
                          </span>
                          <span className="text-xs font-semibold text-slate-100">{d.target_name}</span>
                          <span className="text-[10px] tabular-nums text-slate-500">within {d.within_minutes}m</span>
                          {d.responder_types.map((t) => (
                            <ResponderChip key={t} type={t} />
                          ))}
                          {d.contested && (
                            <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-300">contested</span>
                          )}
                        </div>
                        <p className="text-xs text-slate-300">{d.directive}</p>
                        <p className="mt-1 text-[11px] text-slate-500">{d.justification}</p>
                      </div>
                    ))}
                </div>
              </Card>

              <Card>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Responder allocation</h3>
                <p className="mb-3 text-[11px] text-slate-500">{result.allocation.summary}</p>

                <div className="mb-3 flex flex-wrap gap-2">
                  {Object.entries(result.allocation.pool).map(([type, total]) => {
                    const left = result.allocation.remaining[type] ?? 0
                    const used = total - left
                    const contended = result.allocation.contended_types.includes(type as ResponderType)
                    return (
                      <div
                        key={type}
                        className={`rounded-lg border px-3 py-2 ${
                          contended ? 'border-red-500/40 bg-red-500/5' : 'border-white/10 bg-white/[0.02]'
                        }`}
                      >
                        <div className="text-[10px] uppercase tracking-wide text-slate-500">{type}</div>
                        <div className="text-sm font-bold tabular-nums text-slate-200">
                          {used}
                          <span className="text-slate-600">/{total}</span>
                        </div>
                        {contended && <div className="text-[10px] text-red-400">over-subscribed</div>}
                      </div>
                    )
                  })}
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-[10px] uppercase tracking-wide text-slate-600">
                      <tr>
                        <th className="pb-1 pr-3">Target</th>
                        <th className="pb-1 pr-3">Desk</th>
                        <th className="pb-1 pr-3">Type</th>
                        <th className="pb-1 pr-3 text-right">Asked</th>
                        <th className="pb-1 text-right">Got</th>
                      </tr>
                    </thead>
                    <tbody className="text-slate-400">
                      {result.allocation.allocations.map((a) => (
                        <tr key={a.demand_id} className={a.fully_met ? '' : 'text-red-300'}>
                          <td className="py-1 pr-3">{a.target_name}</td>
                          <td className="py-1 pr-3 text-slate-600">{a.source}</td>
                          <td className="py-1 pr-3">{a.responder_type}</td>
                          <td className="py-1 pr-3 text-right tabular-nums">{a.units_requested}</td>
                          <td className="py-1 text-right font-semibold tabular-nums">{a.units_granted}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {shortfalls.length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-white/5 pt-3 text-[11px] text-slate-500">
                    {shortfalls.map((a) => (
                      <p key={a.demand_id}>
                        <span className="text-slate-400">{a.target_name}:</span> {a.shortfall_reason}
                      </p>
                    ))}
                  </div>
                )}
              </Card>

              {result.critique && (
                <Card className="border-indigo-400/25 bg-indigo-500/[0.04]">
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-indigo-300">
                    Independent red-team review
                  </h3>
                  <Prose className="mb-3 text-xs text-slate-400">{result.critique.overall_verdict}</Prose>

                  {result.critique.single_points_of_failure.length > 0 && (
                    <>
                      <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                        Single points of failure
                      </h4>
                      <ul className="mb-3 space-y-1 text-xs text-slate-400">
                        {result.critique.single_points_of_failure.map((s, i) => (
                          <li key={i}>• {s}</li>
                        ))}
                      </ul>
                    </>
                  )}

                  {result.critique.weaknesses.length === 0 ? (
                    <p className="text-xs text-slate-500">The reviewer found no material weaknesses.</p>
                  ) : (
                    <div className="space-y-2">
                      {result.critique.weaknesses.map((w, i) => (
                        <div key={i} className="rounded-lg border border-white/5 bg-black/20 p-3">
                          <div className="mb-1 flex flex-wrap items-center gap-2">
                            <RiskBadge level={w.severity} />
                            <span className="text-xs font-semibold text-slate-200">{w.weakness}</span>
                          </div>
                          <p className="text-[11px] text-slate-500">
                            <span className="text-slate-400">Breaks under:</span> {w.breaks_under}
                          </p>
                          <p className="mt-1 text-[11px] text-slate-500">
                            <span className="text-slate-400">Mitigation:</span> {w.suggested_mitigation}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
