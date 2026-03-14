from __future__ import annotations

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.domain.models import ActivityEvent, ConnectorSource


class SlackEnterpriseGridAdapter(ConnectorAdapter):
    source = ConnectorSource.SLACK

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def validate(self) -> dict[str, object]:
        missing_fields = []
        if not self._settings.slack_bot_token:
            missing_fields.append("SLACK_BOT_TOKEN")
        return {
            "ok": not missing_fields,
            "configured": not missing_fields,
            "source": self.source.value,
            "missing_fields": missing_fields,
            "message": (
                "Slack Enterprise Grid is connected."
                if not missing_fields
                else "Connect Slack Enterprise Grid to receive real mentions and channel activity."
            ),
        }

    async def poll_events(self) -> list[ActivityEvent]:
        return []

    async def handle_webhook(self, payload: dict[str, object]) -> ActivityEvent:
        event = payload.get("event", {}) if isinstance(payload.get("event"), dict) else {}
        return ActivityEvent(
            source=self.source,
            event_type=str(event.get("type", "slack.message")),
            title=str(event.get("text", "Slack activity"))[:80] or "Slack activity",
            body=str(event.get("text", "Slack event received.")),
            external_id=str(event.get("client_msg_id", payload.get("event_id", "slack-event"))),
            actor=str(event.get("user")) if event.get("user") else None,
            metadata=payload,
        )

    async def fetch_context(self, event: ActivityEvent) -> dict[str, object]:
        return {"my_user_id": self._settings.slack_my_user_id}

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
