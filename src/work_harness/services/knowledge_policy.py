from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from work_harness.config import Settings
from work_harness.domain.models import ActivityEvent, ConnectorSource


@dataclass
class StoreabilityDecision:
    storeable: bool
    scope_type: str | None
    scope_key: str | None
    record_key: str
    canonical_url: str | None
    reason: str


def evaluate_storeability(
    event: ActivityEvent,
    settings: Settings,
) -> StoreabilityDecision:
    if event.source == ConnectorSource.JIRA:
        return _evaluate_jira(event, settings)
    if event.source == ConnectorSource.CONFLUENCE:
        return _evaluate_confluence(event, settings)
    if event.source == ConnectorSource.SLACK:
        return _evaluate_slack(event, settings)
    if event.source == ConnectorSource.GITHUB:
        return _evaluate_github(event, settings)
    return StoreabilityDecision(
        storeable=True,
        scope_type=None,
        scope_key=None,
        record_key=event.external_id,
        canonical_url=None,
        reason="System events can be stored by default.",
    )


def build_search_query(event: ActivityEvent) -> str:
    return " ".join(
        value.strip()
        for value in (event.title, event.body, event.event_type, event.actor or "")
        if value and value.strip()
    )


def build_searchable_text(
    event: ActivityEvent,
    summary: str,
    final_summary: str,
    keywords: list[str],
) -> str:
    parts = [event.title, summary, final_summary, *keywords]
    return " ".join(part.strip() for part in parts if part and part.strip())[:2000]


def _evaluate_jira(event: ActivityEvent, settings: Settings) -> StoreabilityDecision:
    issue = _as_dict(event.metadata.get("issue"))
    issue_key = _first_non_empty(
        issue.get("key"),
        _extract_issue_key(event.title),
        event.external_id,
    )
    project_key = issue_key.split("-", 1)[0] if issue_key and "-" in issue_key else None
    allowed_projects = _split_csv(settings.jira_projects)
    storeable = bool(project_key and project_key in allowed_projects)
    canonical_url = (
        f"{settings.jira_base_url.rstrip('/')}/browse/{issue_key}"
        if settings.jira_base_url and issue_key and "-" in issue_key
        else None
    )
    return StoreabilityDecision(
        storeable=storeable,
        scope_type="project",
        scope_key=project_key,
        record_key=issue_key,
        canonical_url=canonical_url,
        reason=(
            "Jira issue project is allowlisted."
            if storeable
            else "Jira issue project is outside the configured allowlist."
        ),
    )


def _evaluate_confluence(event: ActivityEvent, settings: Settings) -> StoreabilityDecision:
    space = _as_dict(event.metadata.get("space"))
    page = _as_dict(event.metadata.get("page"))
    page_links = _as_dict(page.get("_links"))
    space_key = _first_non_empty(
        space.get("key"),
        page.get("spaceKey"),
        _as_dict(page.get("space")).get("key"),
    )
    allowed_spaces = _split_csv(settings.confluence_spaces)
    storeable = bool(space_key and space_key in allowed_spaces)
    base_url = settings.confluence_url.rstrip("/") if settings.confluence_url else None
    canonical_url = None
    if page_links.get("webui") and base_url:
        canonical_url = f"{base_url}{page_links['webui']}"
    return StoreabilityDecision(
        storeable=storeable,
        scope_type="space",
        scope_key=space_key,
        record_key=str(page.get("id") or event.external_id),
        canonical_url=canonical_url,
        reason=(
            "Confluence page space is allowlisted."
            if storeable
            else "Confluence page space is outside the configured allowlist."
        ),
    )


def _evaluate_slack(event: ActivityEvent, settings: Settings) -> StoreabilityDecision:
    slack_event = _as_dict(event.metadata.get("event"))
    channel = _first_non_empty(
        slack_event.get("channel"),
        event.metadata.get("channel"),
    )
    channel_type = _first_non_empty(
        slack_event.get("channel_type"),
        event.metadata.get("channel_type"),
    )
    allowed_channels = _split_csv(settings.slack_allowed_channels)
    is_direct = bool(channel and (str(channel).startswith("D") or channel_type == "im"))
    storeable = is_direct or bool(channel and channel in allowed_channels)
    reason = (
        "Slack message is in an allowlisted direct or configured channel."
        if storeable
        else "Slack message channel is outside the configured allowlist."
    )
    record_key = _slack_record_key(slack_event, event.external_id)
    return StoreabilityDecision(
        storeable=storeable,
        scope_type="channel",
        scope_key=str(channel) if channel else None,
        record_key=record_key,
        canonical_url=None,
        reason=reason,
    )


def _evaluate_github(event: ActivityEvent, settings: Settings) -> StoreabilityDecision:
    repository = _as_dict(event.metadata.get("repository"))
    pull_request = _as_dict(event.metadata.get("pull_request"))
    issue = _as_dict(event.metadata.get("issue"))
    repo_name = _first_non_empty(repository.get("full_name"), settings.github_repository)
    storeable = bool(
        repo_name
        and settings.github_repository
        and repo_name == settings.github_repository
    )
    canonical_url = _first_non_empty(
        pull_request.get("html_url"),
        issue.get("html_url"),
        repository.get("html_url"),
    )
    record_key = str(
        pull_request.get("id")
        or issue.get("id")
        or event.external_id
    )
    return StoreabilityDecision(
        storeable=storeable,
        scope_type="repository",
        scope_key=str(repo_name) if repo_name else None,
        record_key=record_key,
        canonical_url=canonical_url,
        reason=(
            "GitHub repository is explicitly allowlisted."
            if storeable
            else "GitHub repository is outside the configured allowlist."
        ),
    )


def _split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _extract_issue_key(title: str) -> str | None:
    head = title.split(" ", 1)[0]
    if "-" in head:
        return head.strip()
    return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _slack_record_key(slack_event: dict[str, Any], fallback: str) -> str:
    channel = _first_non_empty(slack_event.get("channel"))
    timestamp = _first_non_empty(
        slack_event.get("thread_ts"),
        slack_event.get("ts"),
        slack_event.get("deleted_ts"),
        _as_dict(slack_event.get("previous_message")).get("ts"),
    )
    if channel and timestamp:
        return f"{channel}:{timestamp}"
    return fallback
