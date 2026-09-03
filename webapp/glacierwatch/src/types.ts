export interface StatusResponse {
  status_text: string
  ready: boolean
  disclaimer: string
}

export interface Site {
  id: string
  name: string
  status: 'active_watch' | 'historical_case_study' | string
}

export interface FileEntry {
  name: string
  label: string
}

export interface StatusBadge {
  level: 'error' | 'warning' | 'success'
  message: string
}

export type RunStatus = 'running' | 'completed' | 'failed'

export interface RunStatusResponse {
  job_id: string
  status: RunStatus
  error: string | null
  status_badge: StatusBadge | null
  sites: Site[] | null
  files: FileEntry[] | null
  summary_text: string | null
}
