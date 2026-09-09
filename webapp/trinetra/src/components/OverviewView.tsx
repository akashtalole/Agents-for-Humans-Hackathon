import { useEffect, useState } from 'react'
import type { ViewKey } from '../App'
import type { CalibrationResult, SitesResponse } from '../types'
import { fetchCalibration } from '../api'
import { Card, SectionTitle } from './ui'

export default function OverviewView({ sites, onNavigate }: { sites: SitesResponse; onNavigate: (v: ViewKey) => void }) {
  const [calibration, setCalibration] = useState<CalibrationResult[] | null>(null)

  useEffect(() => {
    fetchCalibration()
      .then((r) => setCalibration(r.results))
      .catch(() => setCalibration([]))
  }, [])

  const narrowestGhat = [...sites.ghats].sort((a, b) => a.narrowest_approach_m - b.narrowest_approach_m)[0]
  const allCalibrated = calibration !== null && calibration.length > 0 && calibration.every((c) => c.correctly_flagged)

  return (
    <div>
      <SectionTitle eyebrow="Trinetra · त्रिनेत्र" title="Command Overview" hindi="the three-eyed platform" />

      <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Ghats monitored" value={sites.ghats.length} sub="Real, cited Nashik-Trimbakeshwar sites" accent="text-sky-300" />
        <Kpi label="Routes mapped" value={sites.routes.length} sub="Approach lanes & corridors" accent="text-indigo-300" />
        <Kpi
          label="Narrowest approach"
          value={`${narrowestGhat.narrowest_approach_m}m`}
          sub={narrowestGhat.name}
          accent="text-amber-300"
        />
        <Kpi
          label="Calibration"
          value={calibration === null ? '…' : `${calibration.filter((c) => c.correctly_flagged).length} / ${calibration.length}`}
          sub="Disasters flagged, controls held"
          accent={allCalibrated ? 'text-emerald-300' : 'text-red-300'}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="mb-1 text-sm font-semibold text-white">The three pillars</h2>
          <p className="mb-4 text-sm text-slate-400">
            Trinetra means "the three-eyed one" — the literal meaning of Trimbakeshwar. Three eyes, three services.
          </p>
          <div className="space-y-3">
            <PillarRow
              icon="🧑‍🤝‍🧑"
              title="Yatri Netra"
              hindi="यात्री नेत्र"
              desc="Multilingual pilgrim guidance, crowd advisories, and emergency escalation — grounded only in real bundled site data."
              action={() => onNavigate('pilgrim')}
            />
            <PillarRow
              icon="🛡️"
              title="Prashasan Netra"
              hindi="प्रशासन नेत्र"
              desc="NTKMA/NMC command advisory — reads crowd signals and recommends interventions a human always approves."
              action={() => onNavigate('admin')}
            />
            <PillarRow
              icon="🔮"
              title="Bhavishya Netra"
              hindi="भविष्य नेत्र"
              desc="A crowd digital-twin: simulate a scenario minute by minute, watch risk build in real time, before it happens for real."
              action={() => onNavigate('twin')}
            />
          </div>
        </Card>

        <Card>
          <h2 className="mb-1 text-sm font-semibold text-white">Grounded in real history</h2>
          <p className="mb-4 text-sm text-slate-400">Bhavishya Netra is calibrated against two documented Kumbh crowd-crush disasters.</p>
          <div className="space-y-3">
            <HistoryFact year="2003" place="Nashik, Kalaram Mandir" detail="39 dead — barricade failure on a 1.8m lane" />
            <HistoryFact year="2025" place="Prayagraj, Sangam Nose" detail="30+ dead — pre-dawn barricade collapse" />
          </div>
          <button
            onClick={() => onNavigate('calibration')}
            className="mt-4 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-white/10"
          >
            View calibration results →
          </button>
        </Card>
      </div>
    </div>
  )
}

function Kpi({ label, value, sub, accent }: { label: string; value: string | number; sub: string; accent: string }) {
  return (
    <Card>
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-3xl font-bold tabular-nums ${accent}`}>{value}</div>
      <div className="mt-1 truncate text-xs text-slate-500">{sub}</div>
    </Card>
  )
}

function PillarRow({
  icon,
  title,
  hindi,
  desc,
  action,
}: {
  icon: string
  title: string
  hindi: string
  desc: string
  action: () => void
}) {
  return (
    <button
      onClick={action}
      className="flex w-full items-start gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4 text-left transition hover:border-saffron-400/30 hover:bg-white/[0.05]"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/5 text-lg">{icon}</div>
      <div>
        <div className="flex items-baseline gap-2">
          <span className="font-semibold text-white">{title}</span>
          <span className="text-xs text-slate-500">{hindi}</span>
        </div>
        <p className="mt-0.5 text-sm text-slate-400">{desc}</p>
      </div>
    </button>
  )
}

function HistoryFact({ year, place, detail }: { year: string; place: string; detail: string }) {
  return (
    <div className="flex gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-3">
      <div className="shrink-0 rounded-md bg-red-500/10 px-2 py-1 text-xs font-bold text-red-300">{year}</div>
      <div>
        <div className="text-sm font-medium text-slate-200">{place}</div>
        <div className="text-xs text-slate-500">{detail}</div>
      </div>
    </div>
  )
}
