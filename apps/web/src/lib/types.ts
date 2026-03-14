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
  ok: boolean;
  configured: boolean;
  missing_fields: string[];
  message: string;
  identity?: string | null;
  capabilities: ConnectorCapability[];
  subscriptions: EventSubscription[];
  recommended_event_keys: string[];
  selected_event_keys: string[];
  advisory: string;
  config_fields: ConnectorConfigField[];
  webhook?: WebhookProviderMetadata | null;
}

export interface ConnectorCapability {
  key: string;
  label: string;
  status: "verified" | "blocked" | "missing_config" | "unknown";
  detail: string;
  evidence: string[];
}

export interface EventSubscription {
  key: string;
  label: string;
  description: string;
  required_capabilities: string[];
  recommended: boolean;
  selected: boolean;
  available: boolean;
}

export interface ConnectorConfigField {
  key: string;
  label: string;
  placeholder: string;
  help_text: string;
  required: boolean;
  sensitive: boolean;
  value?: string | null;
  is_set: boolean;
}

export interface WebhookProviderMetadata {
  provider: string;
  callback_path: string;
  callback_url: string;
  secret_env_key?: string | null;
  verification_mode: string;
  recommended_events: string[];
  setup_notes: string[];
}
