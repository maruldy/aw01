from pathlib import Path

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings


def test_ingress_creates_and_lists_work_items() -> None:
    client = TestClient(create_app(Settings(knowledge_db_path=Path("./data/test_api_ingress.db"))))

    create_response = client.post(
        "/ingress/slack",
        json={
            "event_type": "slack.mention",
            "title": "Mentioned in #platform",
            "body": "Can someone explain why the deploy failed?",
            "external_id": "evt-1",
            "actor": "U123",
        },
    )
    assert create_response.status_code == 202
    assert create_response.json()["processed"] is True

    list_response = client.get("/work-items")
    assert list_response.status_code == 200

    payload = list_response.json()
    assert payload["items"]
    assert payload["items"][0]["source"] == "slack"


def test_accept_decision_updates_work_item() -> None:
    client = TestClient(create_app(Settings(knowledge_db_path=Path("./data/test_api_decision.db"))))

    create_response = client.post(
        "/ingress/github",
        json={
            "event_type": "github.review_requested",
            "title": "Review requested",
            "body": "Please prepare a fix",
            "external_id": "evt-2",
            "actor": "octocat",
        },
    )
    assert create_response.json()["processed"] is True
    work_item_id = create_response.json()["work_item"]["id"]

    decision_response = client.post(
        f"/work-items/{work_item_id}/decision",
        json={"decision": "accept", "comment": "Proceed with a draft PR."},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "accepted"
