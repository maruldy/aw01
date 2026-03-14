from pathlib import Path

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings


def test_jira_terminal_webhook_upserts_knowledge() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_knowledge_jira.db"),
        jira_projects="OPS",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/webhooks/jira",
            json={
                "webhookEvent": "jira:issue_updated",
                "issue": {
                    "id": "10000",
                    "key": "OPS-1",
                    "fields": {
                        "summary": "Resolve replication lag",
                        "description": "Database incident resolved",
                        "status": {"name": "Done"},
                        "resolution": {"name": "Fixed"},
                    },
                },
                "user": {"displayName": "Daeyoung"},
            },
        )

        assert response.status_code == 202
        assert response.json()["knowledge_action"] == "upsert"

        recent = client.get("/knowledge/recent").json()["items"]
        assert len(recent) == 1
        assert recent[0]["ticket_key"] == "OPS-1"
        assert recent[0]["source"] == "jira"


def test_confluence_delete_webhook_removes_existing_knowledge() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_knowledge_confluence.db"),
        confluence_spaces="ENG",
    )
    with TestClient(create_app(settings)) as client:
        upsert = client.post(
            "/webhooks/confluence",
            json={
                "eventType": "page_updated",
                "page": {"id": "20000", "title": "Runbook", "space": {"key": "ENG"}},
                "space": {"key": "ENG"},
                "user": {"displayName": "Daeyoung"},
            },
        )
        assert upsert.status_code == 202
        assert upsert.json()["knowledge_action"] == "upsert"

        delete_response = client.post(
            "/webhooks/confluence",
            json={
                "eventType": "page_removed",
                "page": {"id": "20000", "title": "Runbook", "space": {"key": "ENG"}},
                "space": {"key": "ENG"},
                "user": {"displayName": "Daeyoung"},
            },
        )

        assert delete_response.status_code == 202
        assert delete_response.json()["knowledge_action"] == "delete"

        recent = client.get("/knowledge/recent").json()["items"]
        assert recent == []
