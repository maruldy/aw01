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
        assert "backfill" in health_payload
        assert health_payload["knowledge"]["total"] == 0

        stats_response = client.get("/knowledge/stats")
        assert stats_response.status_code == 200
        payload = stats_response.json()
        assert "total" in payload
        assert "avg_iterations" in payload


def test_backfill_and_scheduler_endpoints_return_state() -> None:
    with TestClient(
        create_app(Settings(knowledge_db_path=Path("./data/test_operations_backfill.db")))
    ) as client:
        trigger_response = client.post("/backfill/trigger")
        assert trigger_response.status_code == 200
        assert trigger_response.json()["state"] == "disabled"

        status_response = client.get("/backfill/status")
        assert status_response.status_code == 200
        assert status_response.json()["state"] == "disabled"

        jobs_response = client.get("/scheduler/jobs")
        assert jobs_response.status_code == 200
        assert len(jobs_response.json()["jobs"]) >= 2

        stats_response = client.get("/knowledge/stats")
        assert stats_response.status_code == 200
        assert stats_response.json()["total"] == 0
