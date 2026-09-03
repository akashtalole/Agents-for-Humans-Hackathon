// Thin fetch wrappers over the BidWright FastAPI backend (bidwright/api.py).
// Kept dependency-free (no axios) - this is a small, well-defined surface.

export interface StatusResponse {
  status_text: string;
  ready: boolean;
}

export interface FileDownload {
  name: string;
  label: string;
}

export interface RunFile {
  name: string;
  label: string;
  download?: FileDownload;
}

export interface StatusBadge {
  level: "error" | "warning" | "success";
  message: string;
}

export interface RunStatus {
  job_id: string;
  status: "running" | "completed" | "failed";
  error: string | null;
  status_badge: StatusBadge | null;
  files: RunFile[] | null;
  summary_text: string | null;
}

export async function fetchStatus(): Promise<StatusResponse> {
  const res = await fetch("/api/status");
  if (!res.ok) throw new Error(`GET /api/status failed: ${res.status}`);
  return res.json();
}

export interface CreateRunInput {
  useExample: boolean;
  rfp?: File | null;
  profile?: File | null;
  amendment?: File | null;
}

export async function createRun(input: CreateRunInput): Promise<{ job_id: string }> {
  const form = new FormData();
  form.set("use_example", input.useExample ? "true" : "false");
  if (!input.useExample) {
    if (input.rfp) form.set("rfp", input.rfp);
    if (input.profile) form.set("profile", input.profile);
  }
  if (input.amendment) form.set("amendment", input.amendment);

  const res = await fetch("/api/runs", { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `POST /api/runs failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchRun(jobId: string): Promise<RunStatus> {
  const res = await fetch(`/api/runs/${jobId}`);
  if (!res.ok) throw new Error(`GET /api/runs/${jobId} failed: ${res.status}`);
  return res.json();
}

export async function fetchRunFile(jobId: string, filename: string): Promise<string> {
  const res = await fetch(`/api/runs/${jobId}/files/${encodeURIComponent(filename)}`);
  if (!res.ok) throw new Error(`GET file ${filename} failed: ${res.status}`);
  return res.text();
}

export function runFileUrl(jobId: string, filename: string): string {
  return `/api/runs/${jobId}/files/${encodeURIComponent(filename)}`;
}

export function runEventsUrl(jobId: string): string {
  return `/api/runs/${jobId}/events`;
}
