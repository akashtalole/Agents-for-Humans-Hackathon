import { useState } from 'react'
import type { CommandBrief, SitesResponse } from '../types'
import { getAdminBrief } from '../api'
import { Card, Label, PrimaryButton, RiskBadge, SectionTitle, inputClass } from './ui'

interface SignalInput {
  ghat_id: string
  estimated_occupancy: number
  inflow_rate_per_min: number
  outflow_rate_per_min: number
}

export default function AdminView({ sites }: { sites: SitesResponse }) {
  const [signals, setSignals] = useState<SignalInput[]>(
    sites.ghats.map((g) => ({
      ghat_id: g.id,
      estimated_occupancy: Math.round(g.safe_capacity * 0.6),
      inflow_rate_per_min: g.access_points * 30,
      outflow_rate_per_min: g.access_points * 25,
    })),
  )
  const [brief, setBrief] = useState<CommandBrief | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function updateSignal(ghatId: string, field: keyof SignalInput, value: number) {
    setSignals((prev) => prev.map((s) => (s.ghat_id === ghatId ? { ...s, [field]: value } : s)))
  }

  async function requestBrief() {
    setLoading(true)
    setError(null)
    try {
      const result = await getAdminBrief(signals)
      setBrief(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <SectionTitle eyebrow="Pillar II" title="Prashasan Netra" hindi="प्रशासन नेत्र · NTKMA / NMC command" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <h2 className="mb-1 text-sm font-semibold text-white">Current crowd signals</h2>
          <p className="mb-4 text-xs text-slate-500">
            Synthetic / manually-specified in this build — a real deployment wires this panel to NTKMA's own CCTV/footfall feed
            without changing anything downstream.
          </p>
          <div className="space-y-4">
            {sites.ghats.map((ghat) => {
              const signal = signals.find((s) => s.ghat_id === ghat.id)!
              const pct = Math.round((signal.estimated_occupancy / ghat.safe_capacity) * 100)
              return (
                <div key={ghat.id} className="rounded-xl border border-white/5 bg-white/[0.02] p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-200">{ghat.name}</span>
                    <span className="text-xs tabular-nums text-slate-500">
                      safe capacity {ghat.safe_capacity.toLocaleString()}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={ghat.safe_capacity * 2}
                    step={50}
                    value={signal.estimated_occupancy}
                    onChange={(e) => updateSignal(ghat.id, 'estimated_occupancy', Number(e.target.value))}
                    className="w-full accent-saffron-500"
                  />
                  <div className="mt-1 flex items-center justify-between text-xs">
                    <span className="tabular-nums text-slate-400">
                      {signal.estimated_occupancy.toLocaleString()} people ({pct}%)
                    </span>
                    <span className={pct >= 110 ? 'text-red-400' : pct >= 85 ? 'text-amber-400' : 'text-emerald-400'}>
                      {pct >= 110 ? 'over safe capacity' : pct >= 85 ? 'approaching capacity' : 'within capacity'}
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div>
                      <Label>Inflow /min</Label>
                      <input
                        type="number"
                        value={signal.inflow_rate_per_min}
                        onChange={(e) => updateSignal(ghat.id, 'inflow_rate_per_min', Number(e.target.value))}
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <Label>Outflow /min</Label>
                      <input
                        type="number"
                        value={signal.outflow_rate_per_min}
                        onChange={(e) => updateSignal(ghat.id, 'outflow_rate_per_min', Number(e.target.value))}
                        className={inputClass}
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
          <PrimaryButton onClick={requestBrief} disabled={loading} className="mt-4 w-full">
            {loading ? 'Analyzing signals…' : 'Get Prashasan Command brief'}
          </PrimaryButton>
          {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        </Card>

        <Card className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-white">Command brief</h2>
          {!brief && <p className="text-sm text-slate-500">Set signals and request a brief to see recommendations here.</p>}
          {brief && (
            <div className="trinetra-fade-in space-y-4">
              <div className="flex items-center justify-between">
                <RiskBadge level={brief.overall_status} />
              </div>
              <p className="text-sm text-slate-300">{brief.summary}</p>
              <div className="space-y-2">
                {brief.recommendations.map((rec, i) => (
                  <div key={i} className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-200">{rec.target_name}</span>
                      <RiskBadge level={rec.current_risk} />
                    </div>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-saffron-300">
                      {rec.action.replace(/_/g, ' ')} · within {rec.urgency_minutes}m
                    </div>
                    <p className="text-xs text-slate-400">{rec.rationale}</p>
                  </div>
                ))}
                {brief.recommendations.length === 0 && (
                  <p className="text-sm text-slate-500">No interventions recommended at this time.</p>
                )}
              </div>
              <p className="text-[11px] text-slate-600">
                Every recommendation goes to a human operator — Trinetra never auto-executes a gate closure or dispatch.
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
