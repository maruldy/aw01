from pathlib import Path

from fastapi.testclient import TestClient

from work_harness.api.app import create_app
from work_harness.config import Settings


def test_health_and_knowledge_stats_are_available() -> None:
    with TestClient(
        create_app(Settings(knowledge_db_path=Path("./data/test_operations_health.db")))
    ) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200
        health_payload = health_response.json()
        assert health_payload["ok"] is True
        assert health_payload["knowledge"]["total"] == 0

        stats_response = client.get("/knowledge/stats")
        assert stats_response.status_code == 200
        payload = stats_response.json()
        assert "total" in payload
        assert "avg_iterations" in payload


def test_backfill_endpoints_are_removed_and_scheduler_is_empty() -> None:
    with TestClient(
        create_app(Settings(knowledge_db_path=Path("./data/test_operations_scheduler.db")))
    ) as client:
        trigger_response = client.post("/backfill/trigger")
        assert trigger_response.status_code == 404

        status_response = client.get("/backfill/status")
        assert status_response.status_code == 404

        jobs_response = client.get("/scheduler/jobs")
        assert jobs_response.status_code == 200
        assert jobs_response.json()["jobs"] == []

        stats_response = client.get("/knowledge/stats")
        assert stats_response.status_code == 200
        assert stats_response.json()["total"] == 0
