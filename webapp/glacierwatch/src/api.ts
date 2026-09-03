import type { RunStatusResponse, StatusResponse } from './types'

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    throw new Error(`Request failed: ${resp.status} ${resp.statusText}`)
  }
  return resp.json() as Promise<T>
}

export function fetchStatus(): Promise<StatusResponse> {
  return fetch('/api/status').then(json<StatusResponse>)
}

export function createRun(): Promise<{ job_id: string }> {
  return fetch('/api/runs', { method: 'POST' }).then(json<{ job_id: string }>)
}

export function fetchRun(jobId: string): Promise<RunStatusResponse> {
  return fetch(`/api/runs/${jobId}`).then(json<RunStatusResponse>)
}

export async function fetchFile(jobId: string, filename: string): Promise<string> {
  const resp = await fetch(`/api/runs/${jobId}/files/${encodeURIComponent(filename)}`)
  if (!resp.ok) {
    return `_Not generated._`
  }
  return resp.text()
}

/** Opens an EventSource for a job's activity log, calling `onTool` for each
 * tool-call event and `onDone` exactly once when the stream ends (including
 * on a connection error, so the caller never hangs waiting for `done`). */
export function watchRunEvents(
  jobId: string,
  onTool: (toolName: string) => void,
  onDone: () => void,
): () => void {
  const source = new EventSource(`/api/runs/${jobId}/events`)
  let finished = false

  const finish = () => {
    if (finished) return
    finished = true
    source.close()
    onDone()
  }

  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as { tool?: string; done?: boolean }
      if (data.tool) onTool(data.tool)
      if (data.done) finish()
    } catch {
      // ignore malformed frames
    }
  }
  source.onerror = () => finish()

  return () => {
    finished = true
    source.close()
  }
}
