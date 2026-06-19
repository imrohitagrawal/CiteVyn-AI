from fastapi.testclient import TestClient


def test_health_returns_status_and_request_id(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "citevyn-ai-backend"
    assert body["request_id"].startswith("req_")


def test_dependencies_report_no_external_dependencies(client: TestClient) -> None:
    response = client.get("/health/dependencies")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    # The default test settings point at a working SQLite URL, so the
    # postgres dependency reports a healthy ping. (Post-Slice 2 the
    # route delegates to ``app.core.db.ping_database``.)
    assert body["dependencies"]["postgres"]["status"] == "healthy"
    assert "latency_ms" in body["dependencies"]["postgres"]
    assert body["request_id"].startswith("req_")


def test_index_reports_pre_index_status(client: TestClient) -> None:
    response = client.get("/health/index")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pre_index"
    assert body["active_index"] is None
    assert body["previous_good_index"] is None
    assert body["request_id"].startswith("req_")
