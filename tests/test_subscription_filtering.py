from pathlib import Path

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings


def test_ingress_skips_disabled_subscription() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_ingress_skip.db"))
    with TestClient(create_app(settings)) as client:
        update_response = client.post(
            "/settings/subscriptions/slack",
            json={"selected_event_keys": ["direct_message"]},
        )
        assert update_response.status_code == 200

        ingress_response = client.post(
            "/ingress/slack",
            json={
                "event_type": "slack.mention",
                "title": "Mentioned in #platform",
                "body": "Can someone explain why the deploy failed?",
                "external_id": "evt-skip",
                "actor": "U123",
            },
        )

        assert ingress_response.status_code == 202
        payload = ingress_response.json()
        assert payload["processed"] is False
        assert payload["subscription_key"] == "app_mention"
        assert "disabled" in payload["reason"]
