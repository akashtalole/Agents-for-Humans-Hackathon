// Mirrors the response shapes produced by claimclarity/api.py exactly.

export interface StatusResponse {
  status_text: string
  ready: boolean
}

export interface RunCreatedResponse {
  job_id: string
}

export type JobStatus = 'running' | 'completed' | 'failed'

export interface StatusBadge {
  level: 'error' | 'warning' | 'success' | 'info'
  message: string
}

export interface FileDownload {
  name: string
  label: string
}

export interface RunFile {
  name: string
  label: string
  download?: FileDownload
}

export interface RunStatusResponse {
  job_id: string
  status: JobStatus
  error: string | null
  status_badge: StatusBadge | null
  files: RunFile[] | null
  summary_text: string | null
}

export interface ToolEvent {
  tool: string
}

export interface DoneEvent {
  done: true
}
