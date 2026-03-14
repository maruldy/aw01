from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class ConnectorSource(str, Enum):
    JIRA = "jira"
    CONFLUENCE = "confluence"
    SLACK = "slack"
    GITHUB = "github"
    SYSTEM = "system"


class DecisionType(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    ADVISE = "advise"
    DEFER = "defer"


class WorkItemStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ADVISED = "advised"
    DEFERRED = "deferred"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"


class CapabilityStatus(str, Enum):
    VERIFIED = "verified"
    BLOCKED = "blocked"
    MISSING_CONFIG = "missing_config"
    UNKNOWN = "unknown"


class WebhookProvider(str, Enum):
    GITHUB = "github"
    SLACK = "slack"
    JIRA = "jira"
    CONFLUENCE = "confluence"


class ActivityEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: ConnectorSource
    event_type: str
    title: str
    body: str
    external_id: str
    actor: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class WorkProposal(BaseModel):
    summary: str
    suggested_action: str
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    recommended_agent: str
    context_notes: list[str] = Field(default_factory=list)


class WorkItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    source: ConnectorSource
    event_type: str
    title: str
    body: str
    external_id: str
    actor: str | None = None
    status: WorkItemStatus = WorkItemStatus.PENDING
    proposal: WorkProposal
    decision_comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ExecutionRun(BaseModel):
    thread_id: str
    work_item_id: str
    status: RunStatus = RunStatus.RUNNING
    current_step: str = "triage"
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DecisionPayload(BaseModel):
    decision: DecisionType
    comment: str | None = None


class ExecutionPlan(BaseModel):
    work_item_id: str
    commands: list[str] = Field(default_factory=list)
    requires_approval: bool = True


class ConnectorProfile(BaseModel):
    name: str
    source: ConnectorSource
    mode: Literal[
        "cloud_enterprise",
        "self_hosted_enterprise",
        "public_cloud",
        "mock",
    ] = "cloud_enterprise"
    enabled: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)
    ok: bool = False
    configured: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    message: str = ""
    identity: str | None = None
    capabilities: list["ConnectorCapability"] = Field(default_factory=list)
    subscriptions: list["EventSubscription"] = Field(default_factory=list)
    recommended_event_keys: list[str] = Field(default_factory=list)
    selected_event_keys: list[str] = Field(default_factory=list)
    advisory: str = ""
    config_fields: list["ConnectorConfigField"] = Field(default_factory=list)
    webhook: "WebhookProviderMetadata | None" = None


class ConnectorCapability(BaseModel):
    key: str
    label: str
    status: CapabilityStatus
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)


class EventSubscription(BaseModel):
    key: str
    label: str
    description: str
    required_capabilities: list[str] = Field(default_factory=list)
    recommended: bool = False
    selected: bool = False
    available: bool = False


class ConnectorConfigField(BaseModel):
    key: str
    label: str
    placeholder: str = ""
    help_text: str = ""
    required: bool = False
    sensitive: bool = False
    value: str | None = None
    is_set: bool = False


class SubscriptionPreferenceUpdate(BaseModel):
    selected_event_keys: list[str] = Field(default_factory=list)


class ConnectorConfigUpdate(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class IngressResult(BaseModel):
    processed: bool
    source: ConnectorSource
    subscription_key: str | None = None
    reason: str | None = None
    work_item: WorkItem | None = None
    run: ExecutionRun | None = None


class WebhookVerificationResult(BaseModel):
    accepted: bool
    verified: bool
    verification_method: str
    verification_reason: str
    status_code: int = 202


class WebhookDeliveryEnvelope(BaseModel):
    provider: WebhookProvider
    delivery_id: str
    event_type: str
    verified: bool
    verification_method: str
    verification_reason: str
    headers_json: dict[str, str] = Field(default_factory=dict)
    payload_hash: str
    resource_hint: str | None = None
    actor_hint: str | None = None
    status: str = "accepted"
    received_at: datetime = Field(default_factory=utc_now)


class WebhookProviderMetadata(BaseModel):
    provider: WebhookProvider
    callback_path: str
    callback_url: str
    secret_env_key: str | None = None
    verification_mode: str
    recommended_events: list[str] = Field(default_factory=list)
    setup_notes: list[str] = Field(default_factory=list)


class ToolInvocation(BaseModel):
    tool: str
    args: list[str] = Field(default_factory=list)


class PolicyEvaluation(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str


class AnalysisRecord(BaseModel):
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    ticket_key: str
    core_issue: str
    keywords: list[str] = Field(default_factory=list)
    summary: str
    final_summary: str
    jira_search_results: list[str] = Field(default_factory=list)
    confluence_search_results: list[str] = Field(default_factory=list)
    cross_reference_results: list[str] = Field(default_factory=list)
    iterations: int = 1
    response_language: str = "ko"
    session_id: str | None = None


class GraphResult(BaseModel):
    work_item: WorkItem
    run: ExecutionRun
