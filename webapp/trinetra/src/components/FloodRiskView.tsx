import { useState } from 'react'
import type { FloodRiskResponse, SitesResponse } from '../types'
import { assessFloodRisk } from '../api'
import { Card, Label, PrimaryButton, Prose, RiskBadge, SectionTitle, inputClass } from './ui'

// Anchored to the real documented observations in
// trinetra/data/godavari_hydrology.json - above roughly 20,000 cusecs the
// Godavari crossed its danger mark at Nashik and Ramkund flooded.
const DISCHARGE_PRESETS = [
  { label: 'Quiet', cusecs: 2000 },
  { label: 'Rising', cusecs: 8160 },
  { label: 'Warning', cusecs: 14000 },
  { label: 'Danger (2024 level)', cusecs: 22000 },
]

const STAGE_COLOR: Record<string, string> = {
  normal: 'text-emerald-300',
  rising: 'text-sky-300',
  warning: 'text-amber-300',
  danger: 'text-red-300',
}

export default function FloodRiskView({ sites }: { sites: SitesResponse }) {
  const [discharge, setDischarge] = useState(22000)
  const [elderlyShare, setElderlyShare] = useState(0.4)
  const [occupancy, setOccupancy] = useState<Record<string, number>>(
    Object.fromEntries(sites.ghats.map((g) => [g.id, Math.round(g.safe_capacity * 1.0)])),
  )
  const [result, setResult] = useState<FloodRiskResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(await assessFloodRisk(discharge, occupancy, elderlyShare))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <SectionTitle eyebrow="Compound hazard" title="Godavari Flood Risk" hindi="गोदावरी · dam release into a crowded ghat" />
      <p className="mb-6 max-w-4xl text-sm text-slate-400">
        Gangapur Dam releases into the Godavari upstream of Nashik. Above roughly 20,000 cusecs the river has crossed its danger
        mark and <strong className="text-slate-200">Ramkund and Goda Ghat have actually gone underwater</strong> — temples
        submerged, Ramkund closed for two days. During Kumbh those same ghats hold tens of thousands of people. The question that
        decides whether that's an inconvenience or a disaster isn't whether the river rises — it's{' '}
        <strong className="text-slate-200">whether the ghat can be cleared before the water arrives</strong>, and that depends on
        who is standing on it.
      </p>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-white">Scenario</h2>

          <Label>Gangapur Dam discharge (cusecs)</Label>
          <div className="mb-2 grid grid-cols-2 gap-2">
            {DISCHARGE_PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => setDischarge(p.cusecs)}
                className={`rounded-lg border px-2 py-1.5 text-xs transition ${
                  discharge === p.cusecs
                    ? 'border-saffron-400/50 bg-saffron-500/10 text-saffron-200'
                    : 'border-white/10 bg-white/[0.02] text-slate-400 hover:border-white/20'
                }`}
              >
                {p.label}
                <div className="text-[10px] opacity-70">{p.cusecs.toLocaleString()}</div>
              </button>
            ))}
          </div>
          <input
            type="number"
            value={discharge}
            onChange={(e) => setDischarge(Number(e.target.value))}
            className={`${inputClass} mb-4`}
          />

          <Label>Share of crowd elderly / mobility-limited</Label>
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(elderlyShare * 100)}
            onChange={(e) => setElderlyShare(Number(e.target.value) / 100)}
            className="w-full accent-saffron-500"
          />
          <div className="mb-4 text-xs text-slate-400">
            {Math.round(elderlyShare * 100)}% — Kumbh crowds skew heavily elderly, and they clear a ghat far slower than an
            able-bodied crowd. This slider is the difference between a plan that works on paper and one that works in the water.
          </div>

          <Label>Ghat occupancy</Label>
          <div className="space-y-2">
            {sites.ghats.map((g) => (
              <div key={g.id} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-xs text-slate-400" title={g.name}>
                  {g.name}
                </span>
                {/* inputClass leads with w-full, which wins over an appended
                    w-28 in Tailwind's cascade and would squeeze the ghat name
                    out entirely - so this input is sized explicitly instead. */}
                <input
                  type="number"
                  value={occupancy[g.id] ?? 0}
                  onChange={(e) => setOccupancy((o) => ({ ...o, [g.id]: Number(e.target.value) }))}
                  className={`${inputClass.replace('w-full', 'w-24 shrink-0')}`}
                />
              </div>
            ))}
          </div>

          <PrimaryButton onClick={run} disabled={loading} className="mt-4 w-full">
            {loading ? 'Assessing…' : 'Assess compound risk'}
          </PrimaryButton>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </Card>

        <Card className="xl:col-span-3">
          <h2 className="mb-3 text-sm font-semibold text-white">Can each ghat be cleared in time?</h2>
          {!result && <p className="text-sm text-slate-500">Set a discharge and occupancy, then run the assessment.</p>}
          {result && (
            <div className="trinetra-fade-in space-y-4">
              <div className="flex flex-wrap items-center gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">River stage</div>
                  <div className={`text-lg font-bold uppercase ${STAGE_COLOR[result.assessment.river_stage]}`}>
                    {result.assessment.river_stage}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">Lead time</div>
                  <div className="text-lg font-bold tabular-nums text-slate-200">{result.assessment.lead_time_minutes} min</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">Discharge</div>
                  <div className="text-lg font-bold tabular-nums text-slate-200">
                    {result.assessment.discharge_cusecs.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-slate-500">Rainfall (live)</div>
                  <div className="text-lg font-bold tabular-nums text-slate-200">
                    {result.assessment.recent_rainfall_mm !== null ? `${result.assessment.recent_rainfall_mm} mm` : '—'}
                  </div>
                </div>
                <div className="ml-auto">
                  <RiskBadge level={result.assessment.overall_risk} />
                </div>
              </div>

              {result.assessment.ghat_feasibility.map((f) => {
                const shortfall = f.margin_minutes < 0
                return (
                  <div
                    key={f.ghat_id}
                    className={`rounded-xl border p-4 ${
                      shortfall ? 'border-red-500/40 bg-red-500/5' : 'border-white/5 bg-white/[0.02]'
                    }`}
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-sm font-semibold text-slate-100">{f.ghat_name}</span>
                      <RiskBadge level={f.risk} />
                    </div>
                    {/* Clearance vs lead time, drawn to scale against each other */}
                    <div className="mb-2 space-y-1">
                      <TimeBar
                        label="Time to clear"
                        minutes={f.clearance_minutes}
                        max={Math.max(f.clearance_minutes, f.lead_time_minutes)}
                        color={shortfall ? 'bg-red-500' : 'bg-sky-500'}
                      />
                      <TimeBar
                        label="Water arrives"
                        minutes={f.lead_time_minutes}
                        max={Math.max(f.clearance_minutes, f.lead_time_minutes)}
                        color="bg-slate-500"
                      />
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                      <span>{f.occupancy.toLocaleString()} people</span>
                      <span>{f.effective_egress_per_min.toFixed(0)}/min egress</span>
                      <span className={shortfall ? 'font-semibold text-red-300' : 'text-emerald-300'}>
                        margin {f.margin_minutes > 0 ? '+' : ''}
                        {f.margin_minutes.toFixed(0)} min
                        {shortfall && ' — CANNOT CLEAR IN TIME'}
                      </span>
                    </div>
                  </div>
                )
              })}

              {result.assessment.findings.length > 0 && (
                <div>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Findings</h3>
                  <ul className="space-y-1 text-xs text-slate-400">
                    {result.assessment.findings.map((f, i) => (
                      <li key={i}>• {f}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="rounded-xl border border-saffron-400/20 bg-saffron-500/5 p-4">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-saffron-300">NTKMA advisory</h3>
                <p className="mb-2 text-sm font-medium text-slate-100">{result.advisory.headline}</p>
                <Prose className="mb-3 text-xs text-slate-400">{result.advisory.narrative_summary}</Prose>
                {result.advisory.ghats_to_clear_first.length > 0 && (
                  <p className="mb-3 text-xs text-slate-300">
                    <span className="font-semibold">Clear in order:</span>{' '}
                    {result.advisory.ghats_to_clear_first.join(' → ')}
                  </p>
                )}
                <div className="space-y-2">
                  {result.advisory.recommended_actions.map((rec, i) => (
                    <div key={i} className="rounded-lg border border-white/5 bg-black/20 p-2.5">
                      <div className="mb-0.5 text-xs font-semibold text-saffron-300">
                        {rec.target_name} → {rec.action.replace(/_/g, ' ')} (within {rec.urgency_minutes}m)
                      </div>
                      <Prose className="text-xs text-slate-500">{rec.rationale}</Prose>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function TimeBar({ label, minutes, max, color }: { label: string; minutes: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (minutes / max) * 100) : 0
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-[10px] uppercase tracking-wide text-slate-500">{label}</span>
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/5">
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-14 shrink-0 text-right text-xs tabular-nums text-slate-300">{minutes.toFixed(0)}m</span>
    </div>
  )
}
