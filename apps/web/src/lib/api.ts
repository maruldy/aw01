import type { ConnectorProfile, ExecutionRun, GitHubRepository, WorkItem } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string" && payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Ignore non-JSON error responses.
    }
    throw new Error(detail);
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
  return request<ConnectorProfile>(`/settings/validate/${source}`, { method: "POST" });
}

export async function updateSubscriptions(source: string, selectedEventKeys: string[]) {
  return request<ConnectorProfile>(`/settings/subscriptions/${source}`, {
    method: "POST",
    body: JSON.stringify({ selected_event_keys: selectedEventKeys })
  });
}

export async function updateConnectorConfig(source: string, values: Record<string, string>) {
  return request<ConnectorProfile>(`/settings/config/${source}`, {
    method: "POST",
    body: JSON.stringify({ values })
  });
}

export async function startGitHubConnection(frontendOrigin: string, nextPath: string) {
  return request<{ authorization_url: string }>("/settings/github/connect/start", {
    method: "POST",
    body: JSON.stringify({ frontend_origin: frontendOrigin, next_path: nextPath })
  });
}

export async function getGitHubRepositories() {
  return request<{ repositories: GitHubRepository[] }>("/settings/github/repositories");
}
