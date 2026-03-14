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
    configured: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    message: str = ""


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
