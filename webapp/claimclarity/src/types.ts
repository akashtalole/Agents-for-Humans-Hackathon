// Mirrors the response shapes produced by claimclarity/api.py exactly.

export interface StatusResponse {
  status_text: string
  ready: boolean
}

export interface RunCreatedResponse {
  job_id: string
}

export type JobStatus = 'running' | 'awaiting_approval' | 'completed' | 'rejected' | 'failed'

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

export interface ReviewResult {
  approved: boolean
  issues: string[]
  summary: string
}

export interface GuardrailFinding {
  rule: string
  excerpt: string
  explanation: string
}

export interface GuardrailResult {
  passed: boolean
  findings: GuardrailFinding[]
}

export interface RunStatusResponse {
  job_id: string
  status: JobStatus
  error: string | null
  status_badge: StatusBadge | null
  files: RunFile[] | null
  summary_text: string | null
  draft_text: string | null
  review: ReviewResult | null
  guardrail: GuardrailResult | null
  reject_reason: string | null
}

export interface ToolEvent {
  tool: string
}

export interface DoneEvent {
  done: true
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatHistoryResponse {
  messages: ChatMessage[]
}

export interface ChatReplyResponse {
  reply: string
}
