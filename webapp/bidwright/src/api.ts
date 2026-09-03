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

export interface ReviewVerdict {
  approved: boolean;
  issues: string[];
}

export interface GuardrailFinding {
  rule: string;
  excerpt: string;
  explanation: string;
}

export interface GuardrailResult {
  passed: boolean;
  findings: GuardrailFinding[];
}

export type RunStatusValue = "running" | "awaiting_approval" | "completed" | "rejected" | "failed";

export interface RunStatus {
  job_id: string;
  status: RunStatusValue;
  error: string | null;
  status_badge: StatusBadge | null;
  files: RunFile[] | null;
  summary_text: string | null;
  draft_text: string | null;
  review: ReviewVerdict | null;
  guardrail: GuardrailResult | null;
  reject_reason: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
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

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || `POST ${url} failed: ${res.status}`);
  }
  return res.json();
}

export async function approveRun(jobId: string, editedText?: string): Promise<RunStatus> {
  return postJson(`/api/runs/${jobId}/approve`, editedText !== undefined ? { edited_text: editedText } : {});
}

export async function rejectRun(jobId: string, reason?: string): Promise<RunStatus> {
  return postJson(`/api/runs/${jobId}/reject`, reason !== undefined ? { reason } : {});
}

export async function sendChatMessage(jobId: string, message: string): Promise<{ reply: string }> {
  return postJson(`/api/runs/${jobId}/chat`, { message });
}

export async function fetchChatHistory(jobId: string): Promise<{ messages: ChatMessage[] }> {
  const res = await fetch(`/api/runs/${jobId}/chat`);
  if (!res.ok) throw new Error(`GET /api/runs/${jobId}/chat failed: ${res.status}`);
  return res.json();
}
