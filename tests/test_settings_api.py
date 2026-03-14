from fastapi.testclient import TestClient

from work_harness.api.app import create_app


def test_settings_profiles_lists_available_connectors() -> None:
    with TestClient(create_app()) as client:
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


def test_settings_validate_returns_connector_status() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/settings/validate/slack")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "slack"
        assert "ok" in payload
        assert payload["configured"] is False
        assert "SLACK_BOT_TOKEN" in payload["missing_fields"]
        assert payload["message"]
