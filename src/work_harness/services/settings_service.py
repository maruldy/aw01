from __future__ import annotations

from work_harness.config import Settings
from work_harness.connectors.base import ConnectorAdapter
from work_harness.connectors.factory import build_connector
from work_harness.domain.models import (
    ActivityEvent,
    CapabilityStatus,
    ConnectorCapability,
    ConnectorConfigField,
    ConnectorProfile,
    ConnectorSource,
    WebhookProvider,
    WebhookProviderMetadata,
)
from work_harness.services.settings_advisor import SettingsAdvisor
from work_harness.services.settings_store import SettingsStore

CONFIG_FIELD_DEFINITIONS: dict[ConnectorSource, list[ConnectorConfigField]] = {
    ConnectorSource.JIRA: [
        ConnectorConfigField(
            key="jira_base_url",
            label="Jira base URL",
            placeholder="https://jira.company.internal",
            help_text="Self-hosted Jira base URL.",
            required=True,
        ),
        ConnectorConfigField(
            key="jira_api_token",
            label="Jira PAT",
            placeholder="Enter a read-only personal access token",
            help_text=(
                "Prefer a token limited to read access for issue inspection "
                "and on-demand knowledge sync."
            ),
            required=True,
            sensitive=True,
        ),
        ConnectorConfigField(
            key="jira_projects",
            label="Allowed projects",
            placeholder="PROJ,OPS",
            help_text="Comma-separated projects to watch for alerts and enrichment.",
        ),
    ],
    ConnectorSource.CONFLUENCE: [
        ConnectorConfigField(
            key="confluence_url",
            label="Confluence base URL",
            placeholder="https://confluence.company.internal",
            help_text="Self-hosted Confluence base URL.",
            required=True,
        ),
        ConnectorConfigField(
            key="confluence_api_token",
            label="Confluence PAT",
            placeholder="Enter a read-only personal access token",
            help_text="Prefer read-only access to spaces and content used by the harness.",
            required=True,
            sensitive=True,
        ),
        ConnectorConfigField(
            key="confluence_spaces",
            label="Allowed spaces",
            placeholder="ENG,OPS",
            help_text="Comma-separated spaces allowed for alerts and knowledge sync.",
        ),
    ],
    ConnectorSource.SLACK: [
        ConnectorConfigField(
            key="slack_bot_token",
            label="Slack bot token",
            placeholder="xoxb-...",
            help_text="Used for auth probe and inbound alert validation.",
            required=True,
            sensitive=True,
        ),
        ConnectorConfigField(
            key="slack_user_token",
            label="Slack user token",
            placeholder="xoxp-...",
            help_text="Optional. Only store it if a future workflow explicitly needs it.",
            sensitive=True,
        ),
        ConnectorConfigField(
            key="slack_my_user_id",
            label="Bot or operator user ID",
            placeholder="U12345678",
            help_text="Used to anchor mention-based alert routing.",
        ),
        ConnectorConfigField(
            key="slack_allowed_channels",
            label="Allowed channels",
            placeholder="COPS,CPLATFORM",
            help_text=(
                "Comma-separated Slack channel IDs allowed for knowledge "
                "storage. Direct messages are handled separately."
            ),
        ),
    ],
    ConnectorSource.GITHUB: [
        ConnectorConfigField(
            key="github_base_url",
            label="GitHub API base URL",
            placeholder="https://api.github.com",
            help_text=(
                "Keep the default for GitHub Enterprise Cloud "
                "unless you use a custom API host."
            ),
        ),
        ConnectorConfigField(
            key="github_token",
            label="GitHub token",
            placeholder="ghp_...",
            help_text="Prefer repo read and pull request read only for initial harness setup.",
            required=True,
            sensitive=True,
        ),
        ConnectorConfigField(
            key="github_repository",
            label="Scoped repository",
            placeholder="owner/repo",
            help_text="The harness only watches the repositories you explicitly select.",
            required=True,
        ),
    ],
}


class SettingsService:
    def __init__(
        self,
        base_settings: Settings,
        connectors: dict[ConnectorSource, ConnectorAdapter],
        store: SettingsStore,
        advisor: SettingsAdvisor,
    ) -> None:
        self._base_settings = base_settings
        self._connectors = connectors
        self._store = store
        self._advisor = advisor

    async def list_profiles(self) -> list[ConnectorProfile]:
        profiles = []
        for source in self._connectors:
            profiles.append(await self.get_profile(source))
        return profiles

    async def get_profile(self, source: ConnectorSource) -> ConnectorProfile:
        connector = await self.get_runtime_connector(source)
        validation = await connector.validate()
        capabilities = [
            ConnectorCapability.model_validate(item)
            for item in validation.get("capabilities", [])
        ]
        subscriptions = connector.available_subscriptions()
        recommendation = await self._advisor.recommend(source, capabilities, subscriptions)
        persisted_selection = await self._store.get_selected_event_keys(source.value)
        selected_event_keys = (
            persisted_selection
            if persisted_selection is not None
            else recommendation["recommended_event_keys"]
        )
        verified = {
            capability.key
            for capability in capabilities
            if capability.status == CapabilityStatus.VERIFIED
        }
        hydrated_subscriptions = [
            subscription.model_copy(
                update={
                    "available": set(subscription.required_capabilities).issubset(verified),
                    "recommended": subscription.key in recommendation["recommended_event_keys"],
                    "selected": subscription.key in selected_event_keys,
                }
            )
            for subscription in subscriptions
        ]

        config_fields = await self._build_config_fields(source)
        mode = (
            "self_hosted_enterprise"
            if source in {ConnectorSource.JIRA, ConnectorSource.CONFLUENCE}
            else "cloud_enterprise"
        )
        return ConnectorProfile(
            name=source.value,
            source=source,
            mode=mode,
            settings={},
            ok=bool(validation["ok"]),
            configured=bool(validation["configured"]),
            missing_fields=list(validation["missing_fields"]),
            message=str(validation["message"]),
            identity=validation.get("identity"),
            capabilities=capabilities,
            subscriptions=hydrated_subscriptions,
            recommended_event_keys=list(recommendation["recommended_event_keys"]),
            selected_event_keys=list(selected_event_keys),
            advisory=str(recommendation["advisory"]),
            config_fields=config_fields,
            webhook=self._build_webhook_metadata(source),
        )

    async def update_selected_event_keys(
        self,
        source: ConnectorSource,
        selected_event_keys: list[str],
    ) -> ConnectorProfile:
        await self._store.set_selected_event_keys(source.value, selected_event_keys)
        return await self.get_profile(source)

    async def update_runtime_settings(
        self,
        source: ConnectorSource,
        values: dict[str, str],
    ) -> ConnectorProfile:
        await self._store.set_runtime_settings(source.value, values)
        return await self.get_profile(source)

    async def get_runtime_connector(self, source: ConnectorSource) -> ConnectorAdapter:
        runtime_settings = await self.get_runtime_settings_for_source(source)
        connector = build_connector(source, runtime_settings)
        self._connectors[source] = connector
        return connector

    async def get_runtime_settings_for_source(self, source: ConnectorSource) -> Settings:
        overrides = await self._store.get_runtime_settings(source.value)
        return self._base_settings.model_copy(update=overrides)

    async def should_process_event(
        self,
        source: ConnectorSource,
        event: ActivityEvent,
    ) -> tuple[bool, str | None, str]:
        selected_event_keys = await self._store.get_selected_event_keys(source.value)
        connector = await self.get_runtime_connector(source)
        subscription_key = connector.classify_event(event)
        if selected_event_keys is None or subscription_key is None:
            return True, subscription_key, "No saved subscription filter blocked the event."
        if subscription_key in selected_event_keys:
            return True, subscription_key, "The event matches the saved subscription filter."
        return False, subscription_key, f"The {subscription_key} alert is currently disabled."

    async def _build_config_fields(self, source: ConnectorSource) -> list[ConnectorConfigField]:
        overrides = await self._store.get_runtime_settings(source.value)
        fields = []
        for definition in CONFIG_FIELD_DEFINITIONS[source]:
            current_value = overrides.get(
                definition.key,
                getattr(self._base_settings, definition.key, None),
            )
            fields.append(
                definition.model_copy(
                    update={
                        "value": None if definition.sensitive else current_value,
                        "is_set": bool(current_value),
                    }
                )
            )
        return fields

    def _build_webhook_metadata(
        self,
        source: ConnectorSource,
    ) -> WebhookProviderMetadata:
        base_url = self._base_settings.webhook_base_url.rstrip("/")
        callback_path, secret_env_key, verification_mode, recommended_events, setup_notes = {
            ConnectorSource.GITHUB: (
                "/webhooks/github",
                "GITHUB_WEBHOOK_SECRET",
                "Optional HMAC SHA-256 verification via X-Hub-Signature-256.",
                [
                    "pull_request",
                    "pull_request_review",
                    "pull_request_review_comment",
                    "issues",
                    "issue_comment",
                ],
                [
                    "Register the webhook manually on the target repository or organization.",
                    "Use a secret so the harness can verify delivery signatures before logging.",
                ],
            ),
            ConnectorSource.SLACK: (
                "/webhooks/slack/events",
                "SLACK_SIGNING_SECRET",
                "Slack signature verification via X-Slack-Signature and timestamp.",
                ["app_mention", "message.im", "message.channels"],
                [
                    "Enable Event Subscriptions and point Slack to this callback URL.",
                    "Slack will send a URL verification challenge before live events flow.",
                ],
            ),
            ConnectorSource.JIRA: (
                "/webhooks/jira",
                "JIRA_WEBHOOK_SHARED_SECRET",
                "Optional shared-secret header validation for self-hosted Jira webhooks.",
                [
                    "jira:issue_created",
                    "jira:issue_updated",
                    "comment_created",
                    "issue_generic",
                ],
                [
                    (
                        "Register the webhook in Jira administration for the "
                        "projects you want to watch."
                    ),
                    "If your Jira deployment supports a shared secret header, mirror it in .env.",
                ],
            ),
            ConnectorSource.CONFLUENCE: (
                "/webhooks/confluence",
                "CONFLUENCE_WEBHOOK_SECRET",
                "Optional HMAC SHA-256 verification via X-Hub-Signature.",
                ["page_created", "page_updated", "comment_created"],
                [
                    (
                        "Register the webhook in Confluence administration for "
                        "the spaces you want to watch."
                    ),
                    "Use a secret when available so deliveries can be marked verified.",
                ],
            ),
        }[source]
        return WebhookProviderMetadata(
            provider=WebhookProvider(source.value),
            callback_path=callback_path,
            callback_url=f"{base_url}{callback_path}",
            secret_env_key=secret_env_key,
            verification_mode=verification_mode,
            recommended_events=recommended_events,
            setup_notes=setup_notes,
        )
