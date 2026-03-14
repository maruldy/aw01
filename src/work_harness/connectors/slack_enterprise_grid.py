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


def _has_scope(scopes: list[str], *required: str) -> bool:
    return any(scope in scopes for scope in required)


class SlackEnterpriseGridAdapter(ConnectorAdapter):
    source = ConnectorSource.SLACK

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def validate(self) -> dict[str, object]:
        missing_fields = []
        if not self._settings.slack_bot_token:
            missing_fields.append("SLACK_BOT_TOKEN")

        capabilities = [
            ConnectorCapability(
                key="auth",
                label="Authenticate to Slack",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Validate the bot token with Slack auth.test.",
            ),
            ConnectorCapability(
                key="channels_read",
                label="Read channel list",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Confirm that the token exposes channel membership and listing scopes.",
            ),
            ConnectorCapability(
                key="history_read",
                label="Read message history",
                status=(
                    CapabilityStatus.MISSING_CONFIG
                    if missing_fields
                    else CapabilityStatus.UNKNOWN
                ),
                detail="Confirm that the token can read relevant message history.",
            ),
        ]

        identity = None
        missing_scope_evidence: list[str] = []
        if not missing_fields:
            headers = {"Authorization": f"Bearer {self._settings.slack_bot_token}"}
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    auth_response = await client.post(
                        "https://slack.com/api/auth.test",
                        headers=headers,
                    )
                    oauth_scopes_header = auth_response.headers.get("x-oauth-scopes", "")
                    granted_scopes = [
                        scope.strip()
                        for scope in oauth_scopes_header.split(",")
                        if scope.strip()
                    ]

                    if auth_response.is_success and auth_response.json().get("ok"):
                        identity = auth_response.json().get("user")
                        capabilities[0].status = CapabilityStatus.VERIFIED
                        capabilities[0].detail = "The Slack bot token authenticated successfully."
                    else:
                        capabilities[0].status = CapabilityStatus.BLOCKED
                        capabilities[0].detail = (
                            f"Authentication probe failed with status {auth_response.status_code}."
                        )

                    if _has_scope(
                        granted_scopes,
                        "channels:read",
                        "groups:read",
                        "conversations:read",
                    ):
                        capabilities[1].status = CapabilityStatus.VERIFIED
                        capabilities[1].detail = (
                            "The token exposes channel or conversation list scopes."
                        )
                    else:
                        capabilities[1].status = CapabilityStatus.BLOCKED
                        capabilities[1].detail = "No channel list scope was detected."
                        missing_scope_evidence.append(
                            "Expected one of channels:read, groups:read, conversations:read"
                        )

                    if _has_scope(
                        granted_scopes,
                        "channels:history",
                        "groups:history",
                        "im:history",
                        "mpim:history",
                    ):
                        capabilities[2].status = CapabilityStatus.VERIFIED
                        capabilities[2].detail = "The token exposes at least one history scope."
                    else:
                        capabilities[2].status = CapabilityStatus.BLOCKED
                        capabilities[2].detail = "No message history scope was detected."
                        missing_scope_evidence.append(
                            "Expected one of channels:history, groups:history, "
                            "im:history, mpim:history"
                        )

                    for capability in capabilities:
                        if granted_scopes:
                            capability.evidence.append(
                                f"Granted scopes: {', '.join(granted_scopes)}"
                            )
            except httpx.HTTPError as exc:
                capabilities[0].status = CapabilityStatus.BLOCKED
                capabilities[0].detail = f"Authentication probe failed: {exc}"
                capabilities[1].status = CapabilityStatus.UNKNOWN
                capabilities[2].status = CapabilityStatus.UNKNOWN

        configured = not missing_fields and capabilities[0].status == CapabilityStatus.VERIFIED
        message = (
            "Slack Enterprise Grid is ready for safe inbound alert routing."
            if configured
            else "Connect Slack Enterprise Grid and verify read scopes before enabling live alerts."
        )
        return {
            "ok": configured,
            "configured": configured,
            "source": self.source.value,
            "identity": identity,
            "missing_fields": missing_fields,
            "capabilities": [cap.model_dump(mode="json") for cap in capabilities],
            "message": message,
            "evidence": missing_scope_evidence,
        }

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, object]) -> ActivityEvent:
        event = payload.get("event", {}) if isinstance(payload.get("event"), dict) else {}
        event_type = str(event.get("type", payload.get("event_type", "slack.message")))
        return ActivityEvent(
            source=self.source,
            event_type=event_type,
            title=str(event.get("text", "Slack activity"))[:80] or "Slack activity",
            body=str(event.get("text", "Slack event received.")),
            external_id=str(event.get("client_msg_id", payload.get("event_id", "slack-event"))),
            actor=str(event.get("user")) if event.get("user") else None,
            metadata=payload,
        )

    async def fetch_context(self, event: ActivityEvent) -> dict[str, object]:
        context: dict[str, object] = {"my_user_id": self._settings.slack_my_user_id}
        if not self._settings.slack_bot_token:
            return context

        payload = event.metadata if isinstance(event.metadata, dict) else {}
        slack_event = payload.get("event", {})
        channel = slack_event.get("channel") if isinstance(slack_event, dict) else None
        if not channel:
            return context

        headers = {"Authorization": f"Bearer {self._settings.slack_bot_token}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://slack.com/api/conversations.info",
                    headers=headers,
                    params={"channel": channel},
                )
            if response.is_success and response.json().get("ok"):
                channel_info = response.json().get("channel", {})
                context["remote_resource"] = {
                    "channel": channel_info.get("id"),
                    "name": channel_info.get("name"),
                    "is_private": channel_info.get("is_private"),
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
                key="app_mention",
                label="App mentions",
                description="Create work when the bot is mentioned explicitly.",
                required_capabilities=["auth"],
            ),
            EventSubscription(
                key="direct_message",
                label="Direct messages",
                description="Create work from direct messages sent to the bot.",
                required_capabilities=["auth", "history_read"],
            ),
            EventSubscription(
                key="keyword_watch",
                label="Keyword watch",
                description="Create work when a watched keyword appears in allowed channels.",
                required_capabilities=["auth", "channels_read", "history_read"],
            ),
        ]

    def classify_event(self, event: ActivityEvent) -> str | None:
        lowered = event.event_type.lower()
        if "app_mention" in lowered or "mention" in lowered:
            return "app_mention"
        if "message.im" in lowered or "direct_message" in lowered or "dm" in lowered:
            return "direct_message"
        if "message" in lowered:
            return "keyword_watch"
        return None
