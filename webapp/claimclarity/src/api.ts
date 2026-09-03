import type {
  ChatHistoryResponse,
  ChatReplyResponse,
  RunCreatedResponse,
  RunStatusResponse,
  StatusResponse,
} from './types'

async function asJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = body.detail ?? detail
    } catch {
      // ignore - not JSON
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export function fetchStatus(): Promise<StatusResponse> {
  return fetch('/api/status').then((r) => asJson<StatusResponse>(r))
}

export function createRun(useExample: boolean, files: File[]): Promise<RunCreatedResponse> {
  const form = new FormData()
  form.append('use_example', useExample ? 'true' : 'false')
  for (const file of files) {
    form.append('documents', file)
  }
  return fetch('/api/runs', { method: 'POST', body: form }).then((r) => asJson<RunCreatedResponse>(r))
}

export function fetchRun(jobId: string): Promise<RunStatusResponse> {
  return fetch(`/api/runs/${jobId}`).then((r) => asJson<RunStatusResponse>(r))
}

export function fetchRunFile(jobId: string, filename: string): Promise<string> {
  return fetch(`/api/runs/${jobId}/files/${encodeURIComponent(filename)}`).then((r) => {
    if (!r.ok) throw new Error(`Failed to load ${filename}`)
    return r.text()
  })
}

export function runFileDownloadUrl(jobId: string, filename: string): string {
  return `/api/runs/${jobId}/files/${encodeURIComponent(filename)}`
}

export function runEventsUrl(jobId: string): string {
  return `/api/runs/${jobId}/events`
}

export function approveRun(jobId: string, editedText: string | null): Promise<RunStatusResponse> {
  return fetch(`/api/runs/${jobId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ edited_text: editedText }),
  }).then((r) => asJson<RunStatusResponse>(r))
}

export function rejectRun(jobId: string, reason: string | null): Promise<RunStatusResponse> {
  return fetch(`/api/runs/${jobId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  }).then((r) => asJson<RunStatusResponse>(r))
}

export function fetchChatHistory(jobId: string): Promise<ChatHistoryResponse> {
  return fetch(`/api/runs/${jobId}/chat`).then((r) => asJson<ChatHistoryResponse>(r))
}

export function sendChatMessage(jobId: string, message: string): Promise<ChatReplyResponse> {
  return fetch(`/api/runs/${jobId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  }).then((r) => asJson<ChatReplyResponse>(r))
}
