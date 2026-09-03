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

export type RunStatus = 'running' | 'completed' | 'failed' | 'awaiting_approval' | 'rejected'

export interface AlertForApproval {
  site_id: string
  site_name: string
  text: string
}

export interface ReviewVerdict {
  approved: boolean
  issues: string[]
}

export interface GuardrailFindingOut {
  rule: string
  excerpt: string
  explanation: string
}

export interface GuardrailVerdict {
  passed: boolean
  findings: GuardrailFindingOut[]
}

export interface RunStatusResponse {
  job_id: string
  status: RunStatus
  error: string | null
  status_badge: StatusBadge | null
  sites: Site[] | null
  files: FileEntry[] | null
  summary_text: string | null
  alerts_for_approval: AlertForApproval[] | null
  reviews: Record<string, ReviewVerdict> | null
  guardrails: Record<string, GuardrailVerdict> | null
  reject_reason: string | null
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}
