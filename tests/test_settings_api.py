from pathlib import Path

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings


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
            "/settings/config/github",
            json={
                "values": {
                    "github_token": "secret-token",
                    "github_repository": "maruldy/aw01",
                    "github_base_url": "https://api.github.com",
                }
            },
        )
        assert update_response.status_code == 200
        payload = update_response.json()
        fields_by_key = {field["key"]: field for field in payload["config_fields"]}
        assert fields_by_key["github_token"]["value"] is None
        assert fields_by_key["github_token"]["is_set"] is True
        assert fields_by_key["github_repository"]["value"] == "maruldy/aw01"


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
