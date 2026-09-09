import type {
  CalibrationResult,
  CommandBrief,
  CommandResponse,
  FloodRiskResponse,
  NTKMAAdvisory,
  PilgrimGuidance,
  RumorResponse,
  SafetyTriage,
  SimEvent,
  SimulationReport,
  SitesResponse,
} from './types'

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return res.json()
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || `${url} -> ${res.status}`)
  }
  return res.json()
}

export function fetchStatus() {
  return getJSON<{ status_text: string; ready: boolean }>('/api/status')
}

export function fetchSites() {
  return getJSON<SitesResponse>('/api/sites')
}

export function askPilgrim(text: string, language: string) {
  return postJSON<PilgrimGuidance>('/api/pilgrim/ask', { text, language })
}

export function reportSOS(
  description: string,
  location: string,
  incidentType: string,
  involvesChildrenOrElderly: boolean,
) {
  return postJSON<SafetyTriage>('/api/sos', {
    description,
    location,
    incident_type: incidentType,
    involves_children_or_elderly: involvesChildrenOrElderly,
  })
}

export function getAdminBrief(
  signals: { ghat_id: string; estimated_occupancy: number; inflow_rate_per_min: number; outflow_rate_per_min: number }[],
) {
  return postJSON<CommandBrief>('/api/admin/brief', { signals })
}

export function fetchCalibration() {
  return getJSON<{ results: CalibrationResult[] }>('/api/calibration')
}

export function assessFloodRisk(
  dischargeCusecs: number,
  occupancy: Record<string, number>,
  elderlyShare: number,
) {
  return postJSON<FloodRiskResponse>('/api/flood-risk', {
    discharge_cusecs: dischargeCusecs,
    occupancy,
    elderly_share: elderlyShare,
  })
}

export function triageRumor(text: string, location: string, spreadingFast: boolean) {
  return postJSON<RumorResponse>('/api/rumor', {
    text,
    location,
    spreading_fast: spreadingFast,
  })
}

export async function createSimulation(scenario: {
  name: string
  description: string
  total_pilgrims: number
  duration_minutes: number
  peak_inflow_multiplier: number
  active_ghat_ids: string[]
}) {
  const { job_id } = await postJSON<{ job_id: string }>('/api/simulations', scenario)
  return job_id
}

export function streamSimulation(jobId: string, onEvent: (event: SimEvent) => void): () => void {
  const source = new EventSource(`/api/simulations/${jobId}/events`)
  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data) as SimEvent
    onEvent(event)
    if (event.type === 'done') source.close()
  }
  source.onerror = () => {
    source.close()
  }
  return () => source.close()
}

export interface SimulationStatusResponse {
  status: 'running' | 'completed' | 'failed'
  error: string | null
  report: SimulationReport | null
  advisory: NTKMAAdvisory | null
}

export function fetchSimulation(jobId: string) {
  return getJSON<SimulationStatusResponse>(`/api/simulations/${jobId}`)
}

export interface CommandRequest {
  discharge_cusecs?: number | null
  occupancy?: Record<string, number>
  elderly_share?: number
  sos?: { description: string; location: string }[]
  rumor?: { text: string; location: string; spreading_fast?: boolean } | null
  run_red_team?: boolean
}

export function runIncidentCommand(body: CommandRequest) {
  return postJSON<CommandResponse>('/api/command', body)
}
