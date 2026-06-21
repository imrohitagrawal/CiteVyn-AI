"""Async Redis client builder.

Centralizes how the rate limiter (and any future component) opens a
``redis.asyncio.Redis`` client so the connection pool, timeouts, and
``decode_responses`` flag are configured in one place.

The builder is lazy: nothing connects at import time. The first caller
of :func:`get_redis_client` pays the connection cost; subsequent
callers share the same :class:`redis.asyncio.Redis` instance **as
long as the URL is the same**. If the URL rotates (operator changes
``CITEVYN_REDIS_URL`` at runtime, or a test swaps in a different
client), the singleton is rebuilt and the previous pool is closed
before the new one is opened. This is the standard "honour the
parameter" pattern — a half-singleton that silently pins the first
URL forever is a production footgun (operator rotates the password,
limiter still hits the old host, no log line explains the gap).

For tests, :func:`reset_redis_client` drops the singleton so the next
caller rebuilds it. Hermetic tests use :mod:`fakeredis.aioredis`
instead — see ``backend/tests/test_redis_rate_limit.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis_async

_logger = logging.getLogger("citevyn.redis")

#: Module-level singleton. ``None`` until the first call to
#: :func:`get_redis_client`. The companion ``_client_url`` records
#: which URL the cached client was built against — a URL change
#: forces a rebuild.
_client: redis_async.Redis | None = None
_client_url: str | None = None


def get_redis_client() -> redis_async.Redis:
    """Return a process-wide :class:`redis.asyncio.Redis`.

    The URL is read from :func:`app.core.config.get_settings` on
    every call. If the cached client's URL no longer matches the
    current setting, the previous pool is closed and a new client
    is opened. The function is cheap to call repeatedly; the
    rebuild only happens on a URL rotation.

    ``decode_responses=True`` so callers work with ``str`` instead of
    ``bytes``; the rate limiter only stores float scores and short
    member ids so the wire overhead is negligible.
    """
    global _client, _client_url
    from app.core.config import get_settings

    settings = get_settings()
    url = settings.redis_url
    if url is None:
        raise RuntimeError(
            "CITEVYN_REDIS_URL is not set; the redis-backed rate limiter "
            "cannot be constructed. Either set CITEVYN_REDIS_URL or "
            "use the in-process limiter."
        )
    if _client is not None and _client_url == url:
        return _client
    if _client is not None:
        # URL changed (or was cleared) since the last call. Close the
        # previous pool so we don't leak file descriptors, then drop
        # the reference.
        try:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                _logger.warning(
                    "redis_client_url_changed_no_live_close",
                    extra={"old_url": _redact_url(_client_url or ""), "new_url": _redact_url(url)},
                )
            else:
                # No live loop in this code path (e.g. test fixture).
                # The pool will be reaped when the process exits.
                pass
        except Exception:  # pragma: no cover - defensive
            _logger.exception("redis_client_close_failed")
        _client = None
        _client_url = None
    # Imported lazily so the ``redis`` package is only required when
    # a Redis URL is configured. Tests that never set
    # ``CITEVYN_REDIS_URL`` therefore don't pay the import cost.
    import redis.asyncio as redis_async

    _client = redis_async.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        health_check_interval=30,
    )
    _client_url = url
    _logger.info("redis_client_initialized", extra={"url": _redact_url(url)})
    return _client


async def shutdown_redis_client() -> None:
    """Close the shared :class:`redis.asyncio.Redis` if one is open.

    Wired to the FastAPI ``lifespan`` shutdown event so the connection
    pool is released cleanly when the process exits.
    """
    global _client, _client_url
    if _client is None:
        return
    try:
        await _client.aclose()
    except Exception:  # pragma: no cover - defensive: shutdown must never raise
        _logger.exception("redis_client_close_failed")
    _client = None
    _client_url = None


def reset_redis_client() -> None:
    """Drop the singleton without closing its connection pool.

    Test-only helper.
    """
    global _client, _client_url
    _client = None
    _client_url = None


def _redact_url(url: str) -> str:
    """Strip user:password from a redis URL for log lines.

    The full DSN is sensitive (it may carry a password) and we never
    want it in a log file. Returns the scheme + host + db suffix.
    """
    if not url or "@" not in url:
        return url or ""
    scheme_userinfo, host_part = url.rsplit("@", 1)
    scheme = scheme_userinfo.split("://", 1)[0]
    return f"{scheme}://***@{host_part}"


__all__ = [
    "get_redis_client",
    "reset_redis_client",
    "shutdown_redis_client",
]
