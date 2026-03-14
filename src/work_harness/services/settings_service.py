from __future__ import annotations

import secrets
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

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

GITHUB_OAUTH_SCOPES = "read:user repo"

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

    async def list_profiles(
        self,
        *,
        validate_connectors: bool = True,
    ) -> list[ConnectorProfile]:
        profiles = []
        for source in self._connectors:
            profiles.append(
                await self.get_profile(source, validate_connectors=validate_connectors)
            )
        return profiles

    async def get_profile(
        self,
        source: ConnectorSource,
        *,
        validate_connectors: bool = True,
    ) -> ConnectorProfile:
        connector = await self.get_runtime_connector(source)
        if validate_connectors:
            validation = await connector.validate()
        else:
            runtime_settings = await self.get_runtime_settings_for_source(source)
            validation = self._build_local_validation(source, runtime_settings)
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

    def _build_local_validation(
        self,
        source: ConnectorSource,
        runtime_settings: Settings,
    ) -> dict[str, object]:
        if source == ConnectorSource.JIRA:
            missing_fields = []
            if not runtime_settings.jira_base_url:
                missing_fields.append("JIRA_BASE_URL")
            if not runtime_settings.jira_api_token:
                missing_fields.append("JIRA_API_TOKEN")
            capabilities = [
                ConnectorCapability(
                    key="auth",
                    label="Authenticate to Jira",
                    status=(
                        CapabilityStatus.MISSING_CONFIG
                        if missing_fields
                        else CapabilityStatus.UNKNOWN
                    ),
                    detail="Validate the Jira token against the self-hosted REST API.",
                ),
                ConnectorCapability(
                    key="issue_read",
                    label="Read issues",
                    status=(
                        CapabilityStatus.MISSING_CONFIG
                        if missing_fields
                        else CapabilityStatus.UNKNOWN
                    ),
                    detail="Read issue payloads needed for event triage.",
                ),
                ConnectorCapability(
                    key="issue_search",
                    label="Search issues",
                    status=(
                        CapabilityStatus.MISSING_CONFIG
                        if missing_fields
                        else CapabilityStatus.UNKNOWN
                    ),
                    detail="Run limited JQL searches for enrichment and local knowledge lookup.",
                ),
            ]
            message = (
                "Connect Jira self-hosted and verify read access before enabling live issue alerts."
                if missing_fields
                else "Configuration loaded. Run validate to confirm Jira access."
            )
        elif source == ConnectorSource.CONFLUENCE:
            missing_fields = []
            if not runtime_settings.confluence_url:
                missing_fields.append("CONFLUENCE_URL")
            if not runtime_settings.confluence_api_token:
                missing_fields.append("CONFLUENCE_API_TOKEN")
            capabilities = [
                ConnectorCapability(
                    key="auth",
                    label="Authenticate to Confluence",
                    status=(
                        CapabilityStatus.MISSING_CONFIG
                        if missing_fields
                        else CapabilityStatus.UNKNOWN
                    ),
                    detail="Validate the Confluence token against the self-hosted REST API.",
                ),
                ConnectorCapability(
                    key="space_read",
                    label="Read spaces",
                    status=(
                        CapabilityStatus.MISSING_CONFIG
                        if missing_fields
                        else CapabilityStatus.UNKNOWN
                    ),
                    detail="Read configured spaces for event context and knowledge sync.",
                ),
                ConnectorCapability(
                    key="content_read",
                    label="Read content",
                    status=(
                        CapabilityStatus.MISSING_CONFIG
                        if missing_fields
                        else CapabilityStatus.UNKNOWN
                    ),
                    detail="Read Confluence pages and comments for enrichment.",
                ),
            ]
            message = (
                "Connect Confluence self-hosted and verify read access before "
                "enabling live content alerts."
                if missing_fields
                else "Configuration loaded. Run validate to confirm Confluence access."
            )
        elif source == ConnectorSource.SLACK:
            missing_fields = []
            if not runtime_settings.slack_bot_token:
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
            message = (
                "Connect Slack Enterprise Grid and verify read scopes before enabling live alerts."
                if missing_fields
                else "Configuration loaded. Run validate to confirm Slack access."
            )
        elif source == ConnectorSource.GITHUB:
            missing_fields = []
            token_missing = not runtime_settings.github_token
            repository_missing = not runtime_settings.github_repository
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
            if token_missing:
                message = (
                    "Connect GitHub Enterprise Cloud and verify repo read access "
                    "before enabling live alerts."
                )
            elif repository_missing:
                message = "GitHub account connected. Select a repository to finish setup."
            else:
                message = "Configuration loaded. Run validate to confirm GitHub access."
        else:
            raise KeyError(source)

        return {
            "ok": False,
            "configured": not missing_fields,
            "source": source.value,
            "identity": None,
            "missing_fields": missing_fields,
            "capabilities": [cap.model_dump(mode="json") for cap in capabilities],
            "message": message,
            "evidence": [],
        }

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

    async def start_github_connection(
        self,
        frontend_origin: str,
        next_path: str = "/settings",
    ) -> str:
        if (
            not self._base_settings.github_client_id
            or not self._base_settings.github_client_secret
        ):
            raise ValueError("GitHub browser connect is not configured on the server.")

        parsed_origin = urlsplit(frontend_origin)
        if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
            raise ValueError("Invalid frontend origin.")
        if not next_path.startswith("/") or next_path.startswith("//"):
            raise ValueError("Invalid frontend path.")

        state = secrets.token_urlsafe(24)
        await self._store.save_oauth_state(
            ConnectorSource.GITHUB.value,
            state,
            frontend_origin.rstrip("/"),
            next_path,
        )
        params = urlencode(
            {
                "client_id": self._base_settings.github_client_id,
                "redirect_uri": self._github_callback_url(),
                "scope": GITHUB_OAUTH_SCOPES,
                "state": state,
            }
        )
        return f"https://github.com/login/oauth/authorize?{params}"

    async def complete_github_connection(self, code: str, state: str) -> str:
        oauth_state = await self._store.consume_oauth_state(state)
        if oauth_state is None or oauth_state["source"] != ConnectorSource.GITHUB.value:
            raise ValueError("Unknown or expired GitHub connection state.")

        access_token = await self._exchange_github_code_for_token(code)
        await self._store.set_runtime_settings(
            ConnectorSource.GITHUB.value,
            {"github_token": access_token},
        )
        return self._build_frontend_redirect(
            oauth_state["frontend_origin"],
            oauth_state["next_path"],
            status="connected",
        )

    async def list_github_repositories(self) -> list[dict[str, object]]:
        runtime_settings = await self.get_runtime_settings_for_source(ConnectorSource.GITHUB)
        if not runtime_settings.github_token:
            raise ValueError("Connect GitHub before loading repositories.")
        return await self._fetch_github_repositories(
            runtime_settings.github_token,
            runtime_settings.github_base_url,
        )

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

    async def _exchange_github_code_for_token(self, code: str) -> str:
        payload = {
            "client_id": self._base_settings.github_client_id,
            "client_secret": self._base_settings.github_client_secret,
            "code": code,
            "redirect_uri": self._github_callback_url(),
        }
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(
            base_url="https://github.com",
            headers=headers,
            timeout=10.0,
        ) as client:
            response = await client.post("/login/oauth/access_token", data=payload)

        if not response.is_success:
            raise ValueError(
                f"GitHub authorization failed with status {response.status_code}."
            )

        data = response.json()
        access_token = str(data.get("access_token") or "").strip()
        if access_token:
            return access_token

        error = str(data.get("error") or "oauth_exchange_failed")
        description = str(data.get("error_description") or "").strip()
        message = error if not description else f"{error}: {description}"
        raise ValueError(f"GitHub authorization failed: {message}")

    async def _fetch_github_repositories(
        self,
        token: str,
        base_url: str,
    ) -> list[dict[str, object]]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=10.0,
        ) as client:
            response = await client.get(
                "/user/repos",
                params={
                    "per_page": 100,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )

        if not response.is_success:
            raise ValueError(
                f"GitHub repository listing failed with status {response.status_code}."
            )

        repositories = []
        for item in response.json():
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or "").strip()
            if not full_name:
                continue
            repositories.append(
                {
                    "full_name": full_name,
                    "private": bool(item.get("private")),
                }
            )
        return repositories

    def _github_callback_url(self) -> str:
        base_url = self._base_settings.webhook_base_url.rstrip("/")
        return f"{base_url}/settings/github/callback"

    def _build_frontend_redirect(
        self,
        frontend_origin: str,
        next_path: str,
        *,
        status: str,
        message: str | None = None,
    ) -> str:
        query = {"github": status}
        if message:
            query["github_message"] = message
        return urlunsplit(
            (
                urlsplit(frontend_origin).scheme,
                urlsplit(frontend_origin).netloc,
                next_path,
                urlencode(query),
                "",
            )
        )

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
