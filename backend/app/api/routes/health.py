import logging
from typing import Any

from fastapi import APIRouter, Request, Response

from app.core.db import ping_database
from app.core.logging import build_log_event

logger = logging.getLogger("citevyn.health")

router = APIRouter(tags=["health"])


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "request_id": _request_id(request),
        "status": "healthy",
        "service": "citevyn-ai-backend",
    }


@router.get("/health/dependencies")
async def health_dependencies(request: Request, response: Response) -> dict[str, Any]:
    """Probe every external dependency and return their health.

    The route delegates to :func:`app.core.db.ping_database` so the
    same redaction rules apply (no DSN, no credentials, no stack
    traces). A 503 is returned when any dependency is unhealthy so a
    load balancer can drain the pod. The failure record is emitted
    here at the route layer (not in the DB module) so CodeQL's
    clear-text-logging flow analysis has no path from the except
    block in ``ping_database`` to a logger call.
    """
    postgres = await ping_database()
    healthy = postgres.get("status") == "healthy"
    if not healthy:
        response.status_code = 503
        logger.warning(
            build_log_event(
                "database_ping_failed",
                latency_ms=postgres.get("latency_ms"),
            )
        )
    return {
        "request_id": _request_id(request),
        "status": "healthy" if healthy else "degraded",
        "dependencies": {"postgres": postgres},
    }


@router.get("/health/index")
def health_index(request: Request) -> dict[str, Any]:
    return {
        "request_id": _request_id(request),
        "status": "pre_index",
        "active_index": None,
        "previous_good_index": None,
        "message": "No active index exists before Slice 2 persistence and indexing.",
    }
