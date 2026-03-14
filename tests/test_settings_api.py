import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings
from work_harness.services.settings_service import SettingsService


def test_settings_profiles_lists_available_connectors() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_settings_profiles.db"))
    with TestClient(create_app(settings)) as client:
        response = client.get("/settings/profiles")
        assert response.status_code == 200
        payload = response.json()
        assert payload["profiles"]
        profiles_by_source = {profile["source"]: profile for profile in payload["profiles"]}
        assert set(profiles_by_source) >= {
            "jira",
            "confluence",
            "slack",
            "github",
        }
        assert profiles_by_source["jira"]["mode"] == "self_hosted_enterprise"
        assert profiles_by_source["confluence"]["mode"] == "self_hosted_enterprise"
        assert profiles_by_source["slack"]["mode"] == "cloud_enterprise"
        assert profiles_by_source["github"]["mode"] == "cloud_enterprise"
        assert profiles_by_source["jira"]["name"] == "jira"
        assert profiles_by_source["confluence"]["name"] == "confluence"
        assert profiles_by_source["slack"]["name"] == "slack"
        assert profiles_by_source["github"]["name"] == "github"
        assert profiles_by_source["jira"]["configured"] is False
        assert "JIRA_BASE_URL" in profiles_by_source["jira"]["missing_fields"]
        assert profiles_by_source["slack"]["message"]
        assert profiles_by_source["slack"]["capabilities"]
        assert profiles_by_source["slack"]["subscriptions"]
        assert profiles_by_source["slack"]["recommended_event_keys"] == []
        assert profiles_by_source["slack"]["selected_event_keys"] == []


def test_settings_validate_returns_connector_status() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_settings_validate.db"))
    with TestClient(create_app(settings)) as client:
        response = client.post("/settings/validate/slack")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "slack"
        assert "ok" in payload
        assert payload["configured"] is False
        assert "SLACK_BOT_TOKEN" in payload["missing_fields"]
        assert payload["message"]


def test_subscription_selection_is_persisted_in_profile() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_settings_selection.db"))
    with TestClient(create_app(settings)) as client:
        update_response = client.post(
            "/settings/subscriptions/slack",
            json={"selected_event_keys": ["app_mention"]},
        )
        assert update_response.status_code == 200

        profiles_response = client.get("/settings/profiles")
        profile = {
            item["source"]: item for item in profiles_response.json()["profiles"]
        }["slack"]

        assert profile["selected_event_keys"] == ["app_mention"]
        subscription = {
            item["key"]: item for item in profile["subscriptions"]
        }["app_mention"]
        assert subscription["selected"] is True


def test_config_update_persists_non_sensitive_values_and_masks_tokens() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_settings_config.db"))
    with TestClient(create_app(settings)) as client:
        update_response = client.post(
            "/settings/config/slack",
            json={
                "values": {
                    "slack_bot_token": "secret-token",
                    "slack_allowed_channels": "COPS,CPLATFORM",
                }
            },
        )
        assert update_response.status_code == 200
        payload = update_response.json()
        fields_by_key = {field["key"]: field for field in payload["config_fields"]}
        assert fields_by_key["slack_bot_token"]["value"] is None
        assert fields_by_key["slack_bot_token"]["is_set"] is True
        assert fields_by_key["slack_allowed_channels"]["value"] == "COPS,CPLATFORM"


def test_github_profile_uses_browser_connect_instead_of_manual_token_input() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_settings_github_profile.db"))
    with TestClient(create_app(settings)) as client:
        response = client.get("/settings/profiles")
        assert response.status_code == 200

        github = {
            item["source"]: item for item in response.json()["profiles"]
        }["github"]
        field_keys = [field["key"] for field in github["config_fields"]]

        assert "github_token" not in field_keys
        assert "github_repository" in field_keys


def test_github_connect_start_returns_authorization_url() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_settings_github_connect_start.db"),
        webhook_base_url="https://harness.example.com",
        github_client_id="client-123",
        github_client_secret="secret-123",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/settings/github/connect/start",
            json={
                "frontend_origin": "http://127.0.0.1:5173",
                "next_path": "/settings",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        parsed = urlsplit(payload["authorization_url"])
        query = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert parsed.netloc == "github.com"
        assert parsed.path == "/login/oauth/authorize"
        assert query["client_id"] == ["client-123"]
        assert query["redirect_uri"] == [
            "https://harness.example.com/settings/github/callback"
        ]
        assert query["scope"] == ["read:user repo"]
        assert query["state"]


def test_github_connect_callback_persists_token_and_redirects_to_settings(
    monkeypatch,
) -> None:
    async def fake_exchange(self: SettingsService, code: str) -> str:
        assert code == "oauth-code"
        return "oauth-token"

    monkeypatch.setattr(
        SettingsService,
        "_exchange_github_code_for_token",
        fake_exchange,
    )

    db_path = Path("./data/test_settings_github_connect_callback.db")
    settings = Settings(
        knowledge_db_path=db_path,
        webhook_base_url="https://harness.example.com",
        github_client_id="client-123",
        github_client_secret="secret-123",
    )
    with TestClient(create_app(settings)) as client:
        start_response = client.post(
            "/settings/github/connect/start",
            json={
                "frontend_origin": "http://127.0.0.1:5173",
                "next_path": "/settings",
            },
        )
        state = parse_qs(urlsplit(start_response.json()["authorization_url"]).query)["state"][0]

        callback_response = client.get(
            f"/settings/github/callback?code=oauth-code&state={state}",
            follow_redirects=False,
        )

    assert callback_response.status_code == 307
    assert callback_response.headers["location"] == "http://127.0.0.1:5173/settings?github=connected"

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT settings_json
            FROM connector_runtime_settings
            WHERE source = 'github'
            """
        ).fetchone()

    assert row is not None
    assert json.loads(row[0])["github_token"] == "oauth-token"


def test_github_repository_list_returns_accessible_repositories(monkeypatch) -> None:
    async def fake_repositories(
        self: SettingsService,
        token: str,
        base_url: str,
    ) -> list[dict[str, object]]:
        assert token == "oauth-token"
        assert base_url == "https://api.github.com"
        return [
            {"full_name": "maruldy/aw01", "private": True},
            {"full_name": "maruldy/demo", "private": False},
        ]

    monkeypatch.setattr(
        SettingsService,
        "_fetch_github_repositories",
        fake_repositories,
    )

    settings = Settings(
        knowledge_db_path=Path("./data/test_settings_github_repositories.db"),
        github_token="oauth-token",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/settings/github/repositories")

    assert response.status_code == 200
    assert response.json()["repositories"] == [
        {"full_name": "maruldy/aw01", "private": True},
        {"full_name": "maruldy/demo", "private": False},
    ]


def test_settings_profiles_include_webhook_setup_metadata() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_settings_webhooks.db"),
        webhook_base_url="https://harness.example.com",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/settings/profiles")
        assert response.status_code == 200

        profiles_by_source = {
            profile["source"]: profile for profile in response.json()["profiles"]
        }
        github = profiles_by_source["github"]["webhook"]
        slack = profiles_by_source["slack"]["webhook"]

        assert github["callback_url"] == "https://harness.example.com/webhooks/github"
        assert github["secret_env_key"] == "GITHUB_WEBHOOK_SECRET"
        assert "pull_request" in github["recommended_events"]

        assert (
            slack["callback_url"]
            == "https://harness.example.com/webhooks/slack/events"
        )
        assert slack["secret_env_key"] == "SLACK_SIGNING_SECRET"
        assert slack["verification_mode"]
