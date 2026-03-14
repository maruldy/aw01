from fastapi.testclient import TestClient

from work_harness.api.app import create_app


def test_health_and_knowledge_stats_are_available() -> None:
    with TestClient(create_app()) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["ok"] is True

        stats_response = client.get("/knowledge/stats")
        assert stats_response.status_code == 200
        payload = stats_response.json()
        assert "total" in payload
        assert "avg_iterations" in payload


def test_bootstrap_and_scheduler_endpoints_return_state() -> None:
    with TestClient(create_app()) as client:
        trigger_response = client.post("/bootstrap/trigger")
        assert trigger_response.status_code == 200

        status_response = client.get("/bootstrap/status")
        assert status_response.status_code == 200
        assert "state" in status_response.json()

        jobs_response = client.get("/scheduler/jobs")
        assert jobs_response.status_code == 200
        assert len(jobs_response.json()["jobs"]) >= 2
