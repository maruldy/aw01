export type WorkItemStatus = "pending" | "accepted" | "rejected" | "advised" | "deferred";

export type ConnectorSource = "jira" | "confluence" | "slack" | "github" | "system";

export interface WorkProposal {
  summary: string;
  suggested_action: string;
  priority: "low" | "medium" | "high" | "critical";
  recommended_agent: string;
  context_notes: string[];
}

export interface WorkItem {
  id: string;
  thread_id: string;
  source: ConnectorSource;
  event_type: string;
  title: string;
  body: string;
  external_id: string;
  actor?: string | null;
  status: WorkItemStatus;
  proposal: WorkProposal;
  decision_comment?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutionRun {
  thread_id: string;
  work_item_id: string;
  status: string;
  current_step: string;
  events: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface ConnectorProfile {
  name: string;
  source: ConnectorSource;
  mode: string;
  enabled: boolean;
  settings: Record<string, unknown>;
  configured: boolean;
  missing_fields: string[];
  message: string;
}
