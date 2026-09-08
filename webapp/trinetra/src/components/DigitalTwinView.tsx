import { useRef, useState } from 'react'
import type { NTKMAAdvisory, SimulationReport, SitesResponse, TickGhatState } from '../types'
import { createSimulation, streamSimulation } from '../api'
import { Card, Label, PrimaryButton, RiskBadge, SectionTitle, inputClass } from './ui'
import NetworkDiagram from './NetworkDiagram'
import OccupancyTimeline, { type TimelinePoint } from './OccupancyTimeline'

interface Preset {
  key: string
  label: string
  name: string
  description: string
  total_pilgrims: number
  duration_minutes: number
  peak_inflow_multiplier: number
  active_ghat_ids: string[]
}

const PRESETS: Preset[] = [
  {
    key: 'routine',
    label: 'Routine day',
    name: 'Routine weekday',
    description: 'Normal weekday flow, no Shahi Snan peak',
    total_pilgrims: 20000,
    duration_minutes: 180,
    peak_inflow_multiplier: 1.0,
    active_ghat_ids: ['ramkund', 'kushavarta'],
  },
  {
    key: 'nashik_2003',
    label: 'Nashik 2003 replay',
    name: 'Nashik 2003 replay: Kalaram Mandir Marg surge',
    description: 'Replays the documented conditions of the 2003 stampede (39 dead)',
    total_pilgrims: 500000,
    duration_minutes: 180,
    peak_inflow_multiplier: 3.2,
    active_ghat_ids: ['kalaram_marg', 'ramkund'],
  },
  {
    key: 'prayagraj_2025',
    label: 'Prayagraj 2025 replay',
    name: 'Prayagraj 2025 replay: pre-dawn Mauni Amavasya surge',
    description: 'Replays the 2025 Sangam Nose barricade-failure conditions (30+ dead)',
    total_pilgrims: 2000000,
    duration_minutes: 120,
    peak_inflow_multiplier: 4.5,
    active_ghat_ids: ['ramkund', 'kushavarta'],
  },
  {
    key: 'mauni_amavasya',
    label: 'Mauni Amavasya 2027',
    name: 'Mauni Amavasya equivalent, all sites',
    description: 'A hypothetical peak-auspicious-day scenario across every mapped site',
    total_pilgrims: 3000000,
    duration_minutes: 300,
    peak_inflow_multiplier: 3.5,
    active_ghat_ids: ['ramkund', 'kalaram_marg', 'kushavarta', 'panchavati_godavari'],
  },
]

type SimStatus = 'idle' | 'running' | 'completed' | 'failed'

export default function DigitalTwinView({ sites }: { sites: SitesResponse }) {
  const [form, setForm] = useState<Preset>(PRESETS[3])
  const [status, setStatus] = useState<SimStatus>('idle')
  const [liveState, setLiveState] = useState<Record<string, TickGhatState>>({})
  const [history, setHistory] = useState<TimelinePoint[]>([])
  const [currentMinute, setCurrentMinute] = useState(0)
  const [report, setReport] = useState<SimulationReport | null>(null)
  const [advisory, setAdvisory] = useState<NTKMAAdvisory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const stopRef = useRef<(() => void) | null>(null)

  function toggleGhat(id: string) {
    setForm((f) => ({
      ...f,
      active_ghat_ids: f.active_ghat_ids.includes(id) ? f.active_ghat_ids.filter((g) => g !== id) : [...f.active_ghat_ids, id],
    }))
  }

  async function run() {
    stopRef.current?.()
    setStatus('running')
    setLiveState({})
    setHistory([])
    setCurrentMinute(0)
    setReport(null)
    setAdvisory(null)
    setError(null)

    try {
      const jobId = await createSimulation({
        name: form.name,
        description: form.description,
        total_pilgrims: form.total_pilgrims,
        duration_minutes: form.duration_minutes,
        peak_inflow_multiplier: form.peak_inflow_multiplier,
        active_ghat_ids: form.active_ghat_ids,
      })

      stopRef.current = streamSimulation(jobId, (event) => {
        if (event.type === 'tick') {
          setCurrentMinute(event.minute)
          setLiveState((prev) => {
            const next = { ...prev }
            for (const [gid, s] of Object.entries(event.ghats)) next[gid] = s
            return next
          })
          setHistory((prev) => [
            ...prev,
            { minute: event.minute, pct: Object.fromEntries(Object.entries(event.ghats).map(([gid, s]) => [gid, s.pct_of_capacity])) },
          ])
        } else if (event.type === 'report') {
          setReport(event.report)
        } else if (event.type === 'advisory') {
          setAdvisory(event.advisory)
        } else if (event.type === 'error') {
          setError(event.message)
          setStatus('failed')
        } else if (event.type === 'done') {
          setStatus((s) => (s === 'failed' ? s : 'completed'))
        }
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setStatus('failed')
    }
  }

  return (
    <div>
      <SectionTitle eyebrow="Pillar III · flagship" title="Bhavishya Netra" hindi="भविष्य नेत्र · crowd digital twin" />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        {/* Scenario builder */}
        <Card className="xl:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-white">Scenario</h2>
          <div className="mb-4 grid grid-cols-2 gap-2">
            {PRESETS.map((p) => (
              <button
                key={p.key}
                onClick={() => setForm(p)}
                className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                  form.key === p.key
                    ? 'border-saffron-400/50 bg-saffron-500/10 text-saffron-200'
                    : 'border-white/10 bg-white/[0.02] text-slate-400 hover:border-white/20'
                }`}
              >
                <div className="font-semibold">{p.label}</div>
              </button>
            ))}
          </div>
          <p className="mb-4 text-xs text-slate-500">{form.description}</p>

          <div className="space-y-3">
            <div>
              <Label>Total pilgrims</Label>
              <input
                type="number"
                value={form.total_pilgrims}
                onChange={(e) => setForm((f) => ({ ...f, total_pilgrims: Number(e.target.value) }))}
                className={inputClass}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Duration (min)</Label>
                <input
                  type="number"
                  value={form.duration_minutes}
                  onChange={(e) => setForm((f) => ({ ...f, duration_minutes: Number(e.target.value) }))}
                  className={inputClass}
                />
              </div>
              <div>
                <Label>Peak multiplier</Label>
                <input
                  type="number"
                  step="0.1"
                  value={form.peak_inflow_multiplier}
                  onChange={(e) => setForm((f) => ({ ...f, peak_inflow_multiplier: Number(e.target.value) }))}
                  className={inputClass}
                />
              </div>
            </div>
            <div>
              <Label>Active sites</Label>
              <div className="flex flex-wrap gap-2">
                {sites.ghats.map((g) => (
                  <button
                    key={g.id}
                    onClick={() => toggleGhat(g.id)}
                    className={`rounded-full border px-2.5 py-1 text-xs transition ${
                      form.active_ghat_ids.includes(g.id)
                        ? 'border-saffron-400/50 bg-saffron-500/15 text-saffron-200'
                        : 'border-white/10 text-slate-500'
                    }`}
                  >
                    {g.name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <PrimaryButton onClick={run} disabled={status === 'running' || form.active_ghat_ids.length === 0} className="mt-4 w-full">
            {status === 'running' ? `Simulating… minute ${currentMinute}/${form.duration_minutes}` : '▶ Run simulation'}
          </PrimaryButton>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </Card>

        {/* Live digital twin */}
        <Card className="xl:col-span-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Live digital twin</h2>
            {status === 'running' && (
              <span className="flex items-center gap-1.5 text-xs text-saffron-300">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-saffron-400" />
                minute {currentMinute} / {form.duration_minutes}
              </span>
            )}
            {status === 'completed' && report && <RiskBadge level={report.overall_risk} />}
          </div>
          <div className="aspect-[16/10] w-full rounded-xl border border-white/5 bg-black/20 p-2">
            <NetworkDiagram ghats={sites.ghats} routes={sites.routes} liveState={liveState} activeGhatIds={form.active_ghat_ids} />
          </div>
          {history.length > 0 && (
            <div className="mt-4">
              <OccupancyTimeline ghats={sites.ghats} activeGhatIds={form.active_ghat_ids} history={history} durationMinutes={form.duration_minutes} />
            </div>
          )}
        </Card>
      </div>

      {report && (
        <div className="trinetra-fade-in mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-white">Per-ghat results</h2>
            <div className="space-y-2">
              {report.ghat_results.map((g) => (
                <div key={g.ghat_id} className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-200">{g.ghat_name}</span>
                    <RiskBadge level={g.risk_level} />
                  </div>
                  <div className="text-xs text-slate-500">
                    Peak {g.peak_occupancy.toLocaleString()} people ({g.peak_occupancy_pct_of_safe_capacity}%) at minute{' '}
                    {g.peak_tick_minute}
                  </div>
                  {g.bottleneck_routes.length > 0 && (
                    <div className="mt-1 text-xs text-amber-400">Bottleneck: {g.bottleneck_routes.join(', ')}</div>
                  )}
                </div>
              ))}
            </div>
            {report.incidents_triggered.length > 0 && (
              <div className="mt-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-400">Incidents flagged</h3>
                <ul className="space-y-1 text-xs text-red-300">
                  {report.incidents_triggered.map((inc, i) => (
                    <li key={i}>• {inc}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold text-white">NTKMA advisory</h2>
            {!advisory && <p className="text-sm text-slate-500">Generating advisory…</p>}
            {advisory && (
              <div className="space-y-4">
                <p className="text-sm text-slate-300">{advisory.narrative_summary}</p>
                <div>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Top concerns</h3>
                  <ul className="space-y-1 text-xs text-slate-400">
                    {advisory.top_concerns.map((c, i) => (
                      <li key={i}>• {c}</li>
                    ))}
                  </ul>
                </div>
                {advisory.recommended_capacity_changes.length > 0 && (
                  <div>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Recommended interventions</h3>
                    <div className="space-y-2">
                      {advisory.recommended_capacity_changes.map((rec, i) => (
                        <div key={i} className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5">
                          <div className="mb-0.5 text-xs font-semibold text-saffron-300">
                            {rec.target_name} → {rec.action.replace(/_/g, ' ')} (within {rec.urgency_minutes}m)
                          </div>
                          <div className="text-xs text-slate-500">{rec.rationale}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}
