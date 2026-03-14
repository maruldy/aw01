import type { ConnectorProfile, ExecutionRun, WorkItem } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function listWorkItems(): Promise<WorkItem[]> {
  const payload = await request<{ items: WorkItem[] }>("/work-items");
  return payload.items;
}

export async function createIngress(source: string, body: Record<string, unknown>) {
  return request<{ work_item: WorkItem; run: ExecutionRun }>(`/ingress/${source}`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export async function decideWorkItem(workItemId: string, decision: string, comment?: string) {
  return request<WorkItem>(`/work-items/${workItemId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, comment })
  });
}

export async function getRun(threadId: string) {
  return request<ExecutionRun>(`/runs/${threadId}`);
}

export async function getKnowledgeStats() {
  return request<{ total: number; avg_iterations: number; by_month: { month: string; count: number }[] }>(
    "/knowledge/stats"
  );
}

export async function getKnowledgeRecent() {
  return request<{ items: Array<Record<string, string>> }>("/knowledge/recent");
}

export async function getHealth() {
  return request<{ ok: boolean; bootstrap: Record<string, unknown>; knowledge: Record<string, unknown> }>("/health");
}

export async function getAuditRecent() {
  return request<{ items: Array<Record<string, unknown>> }>("/audit/recent");
}

export async function getSchedulerJobs() {
  return request<{ jobs: Array<Record<string, string>> }>("/scheduler/jobs");
}

export async function getProfiles() {
  return request<{ profiles: ConnectorProfile[] }>("/settings/profiles");
}

export async function validateProfile(source: string) {
  return request<{ ok: boolean; source: string }>(`/settings/validate/${source}`, { method: "POST" });
}

export async function triggerBootstrap() {
  return request<Record<string, unknown>>("/bootstrap/trigger", { method: "POST" });
}
