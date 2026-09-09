import { useEffect, useState } from 'react'
import { fetchSites, fetchStatus } from './api'
import type { SitesResponse } from './types'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import OverviewView from './components/OverviewView'
import PilgrimView from './components/PilgrimView'
import AdminView from './components/AdminView'
import DigitalTwinView from './components/DigitalTwinView'
import CalibrationView from './components/CalibrationView'
import FloodRiskView from './components/FloodRiskView'
import RumorView from './components/RumorView'
import CommandView from './components/CommandView'
import MeshView from './components/MeshView'

export type ViewKey = 'overview' | 'pilgrim' | 'admin' | 'twin' | 'flood' | 'rumor' | 'command' | 'mesh' | 'calibration'

export default function App() {
  const [view, setView] = useState<ViewKey>('overview')
  const [statusText, setStatusText] = useState<string>('Checking model provider…')
  const [ready, setReady] = useState(false)
  const [sites, setSites] = useState<SitesResponse | null>(null)
  const [sitesError, setSitesError] = useState<string | null>(null)

  useEffect(() => {
    fetchStatus()
      .then((s) => {
        setStatusText(s.status_text)
        setReady(s.ready)
      })
      .catch(() => setStatusText('Could not reach the Trinetra API'))

    fetchSites()
      .then(setSites)
      .catch((err) => setSitesError(err instanceof Error ? err.message : String(err)))
  }, [])

  return (
    <div className="trinetra-grid-bg min-h-screen bg-[#05070d] text-slate-100">
      <div className="flex min-h-screen">
        <Sidebar view={view} onChange={setView} />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar statusText={statusText} ready={ready} />
          <main className="trinetra-scrollbar flex-1 overflow-y-auto px-4 pb-16 pt-6 sm:px-8">
            {sitesError && (
              <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                Could not load site geography: {sitesError}. Is the Trinetra API server running?
              </div>
            )}
            {!sites ? (
              <div className="flex h-64 items-center justify-center text-slate-500">Loading Trinetra…</div>
            ) : (
              <div className="trinetra-fade-in mx-auto max-w-7xl" key={view}>
                {view === 'overview' && <OverviewView sites={sites} onNavigate={setView} />}
                {view === 'pilgrim' && <PilgrimView />}
                {view === 'admin' && <AdminView sites={sites} />}
                {view === 'twin' && <DigitalTwinView sites={sites} />}
                {view === 'flood' && <FloodRiskView sites={sites} />}
                {view === 'rumor' && <RumorView />}
                {view === 'command' && <CommandView sites={sites} />}
                {view === 'mesh' && <MeshView />}
                {view === 'calibration' && <CalibrationView />}
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
