import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as db_module
from app.main import create_app


def test_health_returns_status_and_request_id(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "citevyn-backend"
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


@pytest.fixture
def app_with_session(session: AsyncSession):
    """Build a FastAPI app whose ``get_session`` returns ``session``.

    Pre-Slice 8 the ``/health/index`` route was a hard-coded
    placeholder. Now it reads ``index_versions`` from the DB,
    so the test needs a session with the schema already
    migrated. The ``session`` fixture from ``conftest.py``
    builds that schema, so we just override the dependency.
    """
    app = create_app()

    async def _override():
        yield session

    app.dependency_overrides[db_module.get_session] = _override
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


def test_index_reports_pre_index_status(app_with_session) -> None:
    with TestClient(app_with_session) as client:
        response = client.get("/health/index")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pre_index"
        assert body["active_index"] is None
        assert body["previous_good_index"] is None
        assert body["request_id"].startswith("req_")
