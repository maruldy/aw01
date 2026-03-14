from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings


def _github_signature(secret: str, raw_body: bytes) -> str:
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _slack_signature(secret: str, timestamp: str, raw_body: bytes) -> str:
    basestring = f"v0:{timestamp}:{raw_body.decode()}".encode()
    digest = hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _confluence_signature(secret: str, raw_body: bytes) -> str:
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_github_webhook_accepts_valid_signature_and_logs_delivery() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_github_valid.db"),
        github_webhook_secret="github-secret",
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "action": "review_requested",
            "pull_request": {"id": 12, "title": "Fix race condition"},
            "repository": {"full_name": "maruldy/aw01"},
            "sender": {"login": "octocat"},
        }
        raw_body = json.dumps(payload).encode()

        response = client.post(
            "/webhooks/github",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-1",
                "X-Hub-Signature-256": _github_signature("github-secret", raw_body),
            },
        )

        assert response.status_code == 202
        assert response.json()["accepted"] is True
        assert response.json()["verified"] is True
        assert response.json()["delivery_id"] == "delivery-1"

        deliveries = client.get("/webhooks/deliveries").json()["items"]
        assert deliveries[0]["provider"] == "github"
        assert deliveries[0]["verified"] is True
        assert deliveries[0]["event_type"] == "pull_request"


def test_github_webhook_rejects_invalid_signature_when_secret_is_configured() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_github_invalid.db"),
        github_webhook_secret="github-secret",
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "action": "opened",
            "pull_request": {"id": 13, "title": "Invalid signature"},
            "repository": {"full_name": "maruldy/aw01"},
        }
        raw_body = json.dumps(payload).encode()

        response = client.post(
            "/webhooks/github",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "delivery-invalid",
                "X-Hub-Signature-256": "sha256=bad",
            },
        )

        assert response.status_code == 401
        assert response.json()["accepted"] is False
        assert response.json()["verified"] is False

        deliveries = client.get("/webhooks/deliveries?provider=github").json()["items"]
        assert deliveries[0]["status"] == "rejected"
        assert deliveries[0]["verified"] is False


def test_slack_url_verification_returns_challenge() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_slack_challenge.db"),
        slack_signing_secret="slack-secret",
    )
    with TestClient(create_app(settings)) as client:
        payload = {"type": "url_verification", "challenge": "abc123"}
        raw_body = json.dumps(payload).encode()
        timestamp = str(int(time.time()))

        response = client.post(
            "/webhooks/slack/events",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": _slack_signature("slack-secret", timestamp, raw_body),
            },
        )

        assert response.status_code == 200
        assert response.json()["challenge"] == "abc123"


def test_slack_url_verification_rejects_invalid_signature() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_slack_challenge_invalid.db"),
        slack_signing_secret="slack-secret",
    )
    with TestClient(create_app(settings)) as client:
        payload = {"type": "url_verification", "challenge": "abc123"}
        raw_body = json.dumps(payload).encode()
        timestamp = str(int(time.time()))

        response = client.post(
            "/webhooks/slack/events",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": "v0=bad",
            },
        )

        assert response.status_code == 401
        assert response.json()["accepted"] is False


def test_slack_rejects_stale_or_invalid_signature() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_slack_invalid.db"),
        slack_signing_secret="slack-secret",
    )
    with TestClient(create_app(settings)) as client:
        payload = {"type": "event_callback", "event": {"type": "app_mention", "text": "hello"}}
        raw_body = json.dumps(payload).encode()
        stale_timestamp = str(int(time.time()) - 600)

        response = client.post(
            "/webhooks/slack/events",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": stale_timestamp,
                "X-Slack-Signature": _slack_signature("slack-secret", stale_timestamp, raw_body),
            },
        )

        assert response.status_code == 401
        assert response.json()["accepted"] is False


def test_jira_webhook_accepts_and_marks_unverified_without_shared_secret() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_webhook_jira.db"))
    with TestClient(create_app(settings)) as client:
        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {"id": "10000", "key": "PROJ-1", "fields": {"summary": "Race condition"}},
            "user": {"displayName": "Daeyoung"},
        }

        response = client.post("/webhooks/jira", json=payload)

        assert response.status_code == 202
        assert response.json()["accepted"] is True
        assert response.json()["verified"] is False

        deliveries = client.get("/webhooks/deliveries?provider=jira").json()["items"]
        assert deliveries[0]["event_type"] == "jira:issue_updated"
        assert deliveries[0]["verified"] is False


def test_confluence_webhook_verifies_hmac_when_secret_is_configured() -> None:
    settings = Settings(
        knowledge_db_path=Path("./data/test_webhook_confluence.db"),
        confluence_webhook_secret="confluence-secret",
    )
    with TestClient(create_app(settings)) as client:
        payload = {
            "eventType": "page_updated",
            "page": {"id": "20000", "title": "Runbook"},
            "user": {"displayName": "Daeyoung"},
        }
        raw_body = json.dumps(payload).encode()

        response = client.post(
            "/webhooks/confluence",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": _confluence_signature("confluence-secret", raw_body),
            },
        )

        assert response.status_code == 202
        assert response.json()["accepted"] is True
        assert response.json()["verified"] is True


def test_webhook_deliveries_support_filters() -> None:
    settings = Settings(knowledge_db_path=Path("./data/test_webhook_filters.db"))
    with TestClient(create_app(settings)) as client:
        client.post(
            "/webhooks/jira",
            json={
                "webhookEvent": "jira:issue_created",
                "issue": {"id": "10001", "key": "PROJ-2", "fields": {"summary": "Created"}},
            },
        )
        client.post(
            "/webhooks/confluence",
            json={
                "eventType": "page_updated",
                "page": {"id": "20001", "title": "Guide"},
            },
        )

        response = client.get("/webhooks/deliveries?provider=jira&limit=1")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["provider"] == "jira"
