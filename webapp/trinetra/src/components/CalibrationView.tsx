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
      <SectionTitle eyebrow="Bhavishya Netra" title="Historical calibration" hindi="सत्यापन · real disasters replayed" />
      <p className="mb-6 max-w-3xl text-sm text-slate-400">
        Each case below is a real, documented Kumbh crowd-crush disaster. Bhavishya Netra's simulator replays the documented
        conditions — if it does not come back CRITICAL, its thresholds are not trustworthy enough to use for real planning. This
        runs the pure-code simulation engine directly, with no LLM involved.
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
                  {results.filter((r) => r.correctly_flagged).length} / {results.length} cases correctly flagged
                </div>
                <div className="text-xs text-slate-500">
                  {allCorrect ? 'The simulator is calibrated against every bundled historical case.' : 'Thresholds need retuning.'}
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
                    <div className="text-xs text-slate-500">Real-world deaths: {r.real_world_deaths}</div>
                  </div>
                  <RiskBadge level={r.simulated_peak_risk} />
                </div>
                <div className={`mb-2 text-xs font-semibold ${r.correctly_flagged ? 'text-emerald-400' : 'text-red-400'}`}>
                  {r.correctly_flagged ? '✅ Correctly flagged critical' : '❌ Not flagged critical'}
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
