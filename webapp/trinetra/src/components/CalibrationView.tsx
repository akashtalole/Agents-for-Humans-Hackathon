import { useEffect, useState } from 'react'
import type { CalibrationResult } from '../types'
import { fetchCalibration } from '../api'
import { Card, RiskBadge, SectionTitle } from './ui'

export default function CalibrationView() {
  const [results, setResults] = useState<CalibrationResult[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCalibration()
      .then((r) => setResults(r.results))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  const allCorrect = results !== null && results.every((r) => r.correctly_flagged)

  return (
    <div>
      <SectionTitle eyebrow="Bhavishya Netra" title="Calibration" hindi="सत्यापन · disasters and controls" />
      <p className="mb-3 max-w-3xl text-sm text-slate-400">
        Two kinds of case run here. <strong className="text-slate-300">Historical incidents</strong> replay documented Kumbh
        crowd-crush disasters and must come back CRITICAL. <strong className="text-slate-300">Synthetic controls</strong> are
        constructed, not historical — ordinary and well-managed days the simulator must decline to flag, plus one case that
        routes the same crowd down the 1.8m lane to check the model reacts to routing and not just headcount.
      </p>
      <p className="mb-6 max-w-3xl text-xs text-slate-500">
        The controls are the reason a pass means anything: a suite of disasters alone is passed by a model that always returns
        CRITICAL. A green result here shows the simulator is internally consistent and responds to routing in the expected
        direction — <strong className="text-slate-400">not</strong> that its thresholds are right for the real Nashik ghats,
        since every capacity figure is Trinetra's own estimate rather than NTKMA's. Runs the pure-code engine, no LLM involved.
      </p>

      {error && <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</div>}

      {!results && !error && <div className="text-sm text-slate-500">Running calibration…</div>}

      {results && (
        <>
          <Card className="mb-4">
            <div className="flex items-center gap-3">
              <span className={`text-3xl ${allCorrect ? 'text-emerald-400' : 'text-red-400'}`}>{allCorrect ? '✅' : '⚠️'}</span>
              <div>
                <div className="text-lg font-semibold text-white">
                  {results.filter((r) => r.correctly_flagged).length} / {results.length} cases behaved as expected
                </div>
                <div className="text-xs text-slate-500">
                  {allCorrect
                    ? `${results.filter((r) => r.case_kind === 'historical_incident').length} historical incident(s) flagged, ${results.filter((r) => !r.expect_critical).length} control(s) correctly held.`
                    : 'Thresholds need retuning.'}
                </div>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {results.map((r) => (
              <Card key={r.case_id} className="trinetra-fade-in">
                <div className="mb-3 flex items-start justify-between">
                  <div>
                    <div className="text-sm font-semibold text-white">{r.case_name}</div>
                    <div className="text-xs text-slate-500">
                      {r.case_kind === 'historical_incident'
                        ? `Real-world deaths: ${r.real_world_deaths}`
                        : 'Synthetic control — not a historical event'}
                    </div>
                  </div>
                  <RiskBadge level={r.simulated_peak_risk} />
                </div>
                <div className={`mb-2 text-xs font-semibold ${r.correctly_flagged ? 'text-emerald-400' : 'text-red-400'}`}>
                  {r.correctly_flagged
                    ? r.expect_critical
                      ? '✅ Correctly flagged critical'
                      : '✅ Control held — correctly not flagged'
                    : r.expect_critical
                      ? '❌ Missed — not flagged critical'
                      : '❌ False alarm — flagged a manageable day'}
                </div>
                <p className="text-xs text-slate-500">{r.note}</p>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
