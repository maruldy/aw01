from __future__ import annotations

import httpx

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import (
    ActivityEvent,
    CapabilityStatus,
    ConnectorCapability,
    ConnectorSource,
    EventSubscription,
)


class GitHubEnterpriseCloudAdapter(ConnectorAdapter):
    source = ConnectorSource.GITHUB

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def validate(self) -> dict[str, object]:
        missing_fields = []
        token_missing = not self._settings.github_token
        repository_missing = not self._settings.github_repository
        if token_missing:
            missing_fields.append("GITHUB_TOKEN")
        if repository_missing:
            missing_fields.append("GITHUB_REPOSITORY")

        capabilities = [
            ConnectorCapability(
                key="auth",
                label="Authenticate to GitHub",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if token_missing
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Validate the GitHub token against the REST API.",
            ),
            ConnectorCapability(
                key="repo_read",
                label="Read repository",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if token_missing or repository_missing
                    else CapabilityStatus.UNKNOWN
                ),
                detail=(
                    "Select a repository after connecting GitHub."
                    if repository_missing
                    else "Confirm read access to the configured repository."
                ),
            ),
            ConnectorCapability(
                key="pull_request_read",
                label="Read pull requests",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if token_missing or repository_missing
                    else CapabilityStatus.UNKNOWN
                ),
                detail=(
                    "Select a repository after connecting GitHub."
                    if repository_missing
                    else "Confirm read access to pull request metadata."
                ),
            ),
        ]

        identity = None
        evidence: list[str] = []
        if not token_missing:
            headers = {
                "Authorization": f"Bearer {self._settings.github_token}",
                "Accept": "application/vnd.github+json",
            }
            base_url = self._settings.github_base_url.rstrip("/")
            try:
                async with httpx.AsyncClient(
                    base_url=base_url,
                    headers=headers,
                    timeout=5.0,
                ) as client:
                    user_response = await client.get("/user")
                    if user_response.is_success:
                        identity = user_response.json().get("login")
                        capabilities[0].status = CapabilityStatus.VERIFIED
                        capabilities[0].detail = "The GitHub token authenticated successfully."
                    else:
                        capabilities[0].status = CapabilityStatus.BLOCKED
                        capabilities[0].detail = (
                            f"Authentication probe failed with status {user_response.status_code}."
                        )

                    for header_name in (
                        "x-oauth-scopes",
                        "x-accepted-oauth-scopes",
                        "x-accepted-github-permissions",
                    ):
                        header_value = user_response.headers.get(header_name)
                        if header_value:
                            evidence.append(f"{header_name}: {header_value}")

                    if not repository_missing:
                        repository = self._settings.github_repository
                        repo_response = await client.get(f"/repos/{repository}")
                        if repo_response.is_success:
                            capabilities[1].status = CapabilityStatus.VERIFIED
                            capabilities[1].detail = "The token can read the configured repository."
                        else:
                            capabilities[1].status = CapabilityStatus.BLOCKED
                            capabilities[1].detail = (
                                "Repository read probe failed with status "
                                f"{repo_response.status_code}."
                            )

                        pulls_response = await client.get(
                            f"/repos/{repository}/pulls",
                            params={"per_page": 1, "state": "open"},
                        )
                        if pulls_response.is_success:
                            capabilities[2].status = CapabilityStatus.VERIFIED
                            capabilities[2].detail = "The token can read pull request metadata."
                        else:
                            capabilities[2].status = CapabilityStatus.BLOCKED
                            capabilities[2].detail = (
                                "Pull request probe failed with status "
                                f"{pulls_response.status_code}."
                            )
            except httpx.HTTPError as exc:
                capabilities[0].status = CapabilityStatus.BLOCKED
                capabilities[0].detail = f"Authentication probe failed: {exc}"
                if not repository_missing:
                    capabilities[1].status = CapabilityStatus.UNKNOWN
                    capabilities[2].status = CapabilityStatus.UNKNOWN

        configured = (
            not repository_missing
            and capabilities[0].status == CapabilityStatus.VERIFIED
            and capabilities[1].status == CapabilityStatus.VERIFIED
            and capabilities[2].status == CapabilityStatus.VERIFIED
        )
        if token_missing:
            message = (
                "Connect GitHub Enterprise Cloud and verify repo read access "
                "before enabling live alerts."
            )
        elif repository_missing:
            message = "GitHub account connected. Select a repository to finish setup."
        elif configured:
            message = "GitHub Enterprise Cloud is ready for safe repo-scoped alert routing."
        else:
            message = (
                "GitHub account is connected, but the selected repository "
                "could not be verified."
            )
        return {
            "ok": configured,
            "configured": configured,
            "source": self.source.value,
            "identity": identity,
            "missing_fields": missing_fields,
            "capabilities": [cap.model_dump(mode="json") for cap in capabilities],
            "message": message,
            "evidence": evidence,
        }

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, object]) -> ActivityEvent:
        action = str(payload.get("action", "activity"))
        if payload.get("pull_request") is not None:
            event_family = "pull_request"
            title_source = payload.get("pull_request", {})
        elif payload.get("issue") is not None:
            event_family = "issue"
            title_source = payload.get("issue", {})
        else:
            event_family = str(payload.get("event_name", "event"))
            title_source = payload.get("repository", {})

        title = title_source.get("title") if isinstance(title_source, dict) else None
        if not title:
            repository = (
                payload.get("repository", {})
                if isinstance(payload.get("repository"), dict)
                else {}
            )
            title = repository.get("full_name") or "GitHub activity"

        body = ""
        if isinstance(title_source, dict):
            body = str(title_source.get("body") or "")
        if not body:
            body = f"GitHub action: {event_family}.{action}"

        sender = payload.get("sender", {}) if isinstance(payload.get("sender"), dict) else {}
        return ActivityEvent(
            source=self.source,
            event_type=f"github.{event_family}.{action}",
            title=str(title),
            body=str(body),
            external_id=str(title_source.get("id", payload.get("delivery", "github-event"))),
            actor=str(sender.get("login")) if sender.get("login") else None,
            metadata=payload,
        )

    async def fetch_context(self, event: ActivityEvent) -> dict[str, object]:
        context: dict[str, object] = {"repository": self._settings.github_repository}
        if not self._settings.github_token or not self._settings.github_repository:
            return context

        payload = event.metadata if isinstance(event.metadata, dict) else {}
        pull_request = payload.get("pull_request", {})
        issue = payload.get("issue", {})
        number = None
        endpoint = None
        if isinstance(pull_request, dict) and pull_request.get("number"):
            number = pull_request["number"]
            endpoint = f"/repos/{self._settings.github_repository}/pulls/{number}"
        elif isinstance(issue, dict) and issue.get("number"):
            number = issue["number"]
            endpoint = f"/repos/{self._settings.github_repository}/issues/{number}"
        if endpoint is None:
            return context

        headers = {
            "Authorization": f"Bearer {self._settings.github_token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.github_base_url.rstrip("/"),
                headers=headers,
                timeout=5.0,
            ) as client:
                response = await client.get(endpoint)
            if response.is_success:
                data = response.json()
                context["remote_resource"] = {
                    "number": data.get("number"),
                    "state": data.get("state"),
                    "title": data.get("title"),
                    "updated_at": data.get("updated_at"),
                }
        except httpx.HTTPError:
            return context
        return context

    async def execute_remote_action(
        self,
        action: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "ok": False,
            "source": self.source.value,
            "action": action,
            "message": "Not implemented.",
        }

    def available_subscriptions(self) -> list[EventSubscription]:
        return [
            EventSubscription(
                key="review_requested",
                label="Review requested",
                description="Create work when a pull request review is requested.",
                required_capabilities=["repo_read", "pull_request_read"],
            ),
            EventSubscription(
                key="pull_request_activity",
                label="Pull request activity",
                description="Track key pull request lifecycle changes.",
                required_capabilities=["repo_read", "pull_request_read"],
            ),
            EventSubscription(
                key="issue_activity",
                label="Issue activity",
                description="Track GitHub issues relevant to the selected repository.",
                required_capabilities=["repo_read"],
            ),
        ]

    def classify_event(self, event: ActivityEvent) -> str | None:
        lowered = event.event_type.lower()
        if "review_requested" in lowered:
            return "review_requested"
        if "pull_request" in lowered:
            return "pull_request_activity"
        if "issue" in lowered:
            return "issue_activity"
        return None
