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
            key="github_token",
            label="GitHub PAT",
            placeholder="ghp_... or gho_...",
            help_text=(
                "Personal access token with repo read scope. "
                "Use this when browser OAuth is not configured."
            ),
            required=True,
            sensitive=True,
        ),
        ConnectorConfigField(
            key="github_repository",
            label="Scoped repositories",
            placeholder="owner/repo1,owner/repo2",
            help_text="Comma-separated list of repositories the harness watches.",
        ),
    ],
}

AVAILABLE_REMOTE_ACTIONS: dict[str, list[dict[str, str]]] = {
    "github": [
        {
            "key": "create_issue",
            "label": "Create issue",
            "description": "Create a new issue in a GitHub repository.",
        },
    ],
    "jira": [
        {
            "key": "create_issue",
            "label": "Create issue",
            "description": "Create a new Jira issue in a configured project.",
        },
    ],
    "slack": [
        {
            "key": "send_message",
            "label": "Send message",
            "description": "Send a message to a Slack channel.",
        },
    ],
    "confluence": [
        {
            "key": "create_page",
            "label": "Create page",
            "description": "Create a new Confluence page in a configured space.",
        },
    ],
}


class SettingsService:
    _VALIDATE_CACHE_TTL = 30.0

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
        self._validate_cache: dict[str, tuple[float, dict]] = {}

    async def list_profiles(self) -> list[ConnectorProfile]:
        import asyncio

        return list(await asyncio.gather(
            *(self.get_profile(source) for source in self._connectors)
        ))

    async def get_profile(
        self,
        source: ConnectorSource,
        *,
        force_validate: bool = False,
    ) -> ConnectorProfile:
        connector = await self.get_runtime_connector(source)
        import time

        now = time.monotonic()
        cached = self._validate_cache.get(source.value)
        if not force_validate and cached and (now - cached[0]) < self._VALIDATE_CACHE_TTL:
            validation = cached[1]
        else:
            validation = await connector.validate()
            self._validate_cache[source.value] = (now, validation)
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
            detected_scopes=validation.get("detected_scopes", []),
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

    async def get_allowed_actions(self, source: ConnectorSource) -> list[str]:
        saved = await self._store.get_allowed_actions(source.value)
        return saved if saved is not None else []

    async def get_available_tools(
        self,
        source: ConnectorSource,
    ) -> list[dict[str, object]]:
        if source == ConnectorSource.GITHUB:
            from work_harness.connectors.github_tool_registry import (
                tools_for_scopes,
            )
            profile = await self.get_profile(source)
            return tools_for_scopes(profile.detected_scopes)
        return AVAILABLE_REMOTE_ACTIONS.get(source.value, [])

    async def set_allowed_actions(
        self,
        source: ConnectorSource,
        actions: list[str],
    ) -> list[str]:
        available = await self.get_available_tools(source)
        available_keys = {str(a["key"]) for a in available}
        filtered = [a for a in actions if a in available_keys]
        await self._store.set_allowed_actions(source.value, filtered)
        return filtered

    async def list_github_repositories(self) -> list[dict[str, object]]:
        runtime_settings = await self.get_runtime_settings_for_source(ConnectorSource.GITHUB)
        if not runtime_settings.github_token:
            raise ValueError("Connect GitHub before loading repositories.")
        return await self._fetch_github_repositories(
            runtime_settings.github_token,
            runtime_settings.github_base_url,
        )

    async def list_github_recommended_repos(self) -> list[dict[str, object]]:
        runtime_settings = await self.get_runtime_settings_for_source(ConnectorSource.GITHUB)
        if not runtime_settings.github_token:
            raise ValueError("Connect GitHub before loading recommended repos.")
        return await self._fetch_github_recommended_repos(
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

    async def _fetch_github_recommended_repos(
        self,
        token: str,
        base_url: str,
    ) -> list[dict[str, object]]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        from collections import Counter

        counter: Counter[str] = Counter()
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=10.0,
        ) as client:
            user_response = await client.get("/user")
            if not user_response.is_success:
                return []
            login = user_response.json().get("login")
            if not login:
                return []

            for page in range(1, 4):
                events_response = await client.get(
                    f"/users/{login}/events",
                    params={"per_page": 100, "page": page},
                )
                if not events_response.is_success:
                    break
                events = events_response.json()
                if not events:
                    break
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    repo = event.get("repo")
                    if isinstance(repo, dict):
                        name = str(repo.get("name") or "").strip()
                        if name:
                            counter[name] += 1

        return [
            {"full_name": name, "activity_count": count}
            for name, count in counter.most_common(20)
        ]

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
