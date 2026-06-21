"""Rate limiter for the public + admin routes.

The limiter applies a sliding-window policy per ``user_id`` (a string
the auth dependency returns — ``"demo_user"`` for the demo path,
``"admin"`` for the admin path). On every request we evict timestamps
older than ``window_seconds`` and reject if the remaining count
exceeds the per-window limit for the user's role.

Two implementations
-------------------

* **In-process** — :class:`RateLimiter` is the original Slice 8
  implementation. The bucket is an in-memory ``dict`` protected by an
  :class:`asyncio.Lock`. It is hermetic (no external dependency) and
  is the default in unit tests where there is no Redis service.
* **Redis** — :class:`RedisRateLimiter` uses an atomic Lua script
  (``EVAL``) that does ``ZREMRANGEBYSCORE`` + a conditional
  ``ZADD`` + ``EXPIRE`` in a single server-side step. The script
  only inserts the new hit **if** the post-eviction count is below
  the limit, so a flood of denied requests cannot pin the bucket
  and lock out a legitimate user.

Selection
---------

:func:`get_limiter` returns whichever implementation matches
``settings.redis_url``. Production deploys MUST set
``CITEVYN_REDIS_URL`` so the Redis path is active — leaving the
in-process path in production under-counts under multi-worker
uvicorn.

Wiring
------

The route layer enforces the limit through a FastAPI dependency
(:func:`rate_limited_demo`, :func:`rate_limited_admin`) that
chains the auth dependency and the limiter. Every authenticated
route that returns user data must add one of these — there is no
global middleware, because the auth key and the rate-limit key
must agree. Skipping the dependency silently disables the limit
on that route; the route test suite asserts the dependency is in
place to catch the regression.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Annotated, Protocol

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.errors import APIErrorCode, error_response
from app.core.middleware import get_current_request_id
from app.core.security import require_admin_api_key, require_demo_api_key

if TYPE_CHECKING:
    from redis.asyncio import Redis

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class _LimiterLike(Protocol):
    """Minimum surface the rate-limit policy needs from a limiter."""

    @property
    def window_seconds(self) -> int: ...

    def limit_for(self, *, role: str) -> int: ...

    async def check(self, *, user_id: str, role: str) -> None: ...


# ---------------------------------------------------------------------------
# In-process limiter (Slice 8)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Sliding-window rate limiter, per ``user_id``.

    Threading note: the underlying lock is :class:`asyncio.Lock`
    because FastAPI runs requests on a single event loop. Cross-thread
    use (e.g. a background task) would need a ``threading.Lock`` —
    not used in the MVP.

    Scope: **per-process**. Multi-worker uvicorn deployments
    under-count. Production deploys use :class:`RedisRateLimiter`
    instead; this class is the hermetic / single-process path.

    The limit is read from the ``limits`` dict passed at construction
    time (mapped from :attr:`Settings.rate_limit_*_per_hour`) so the
    operator-tunable env vars are honoured. Unknown roles fall back to
    the demo-user limit so a misconfigured caller cannot bypass by
    sending a bogus role string.
    """

    def __init__(
        self,
        *,
        window_seconds: int,
        demo_user_per_window: int,
        admin_per_window: int,
    ) -> None:
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        if demo_user_per_window < 1 or admin_per_window < 1:
            raise ValueError("per-window limits must be >= 1")
        self._window_seconds = window_seconds
        self._limits: dict[str, int] = {
            "demo_user": demo_user_per_window,
            "admin": admin_per_window,
        }
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def limit_for(self, *, role: str) -> int:
        """Return the per-window hit limit for ``role``."""
        return self._limits.get(role, self._limits["demo_user"])

    async def check(self, *, user_id: str, role: str) -> None:
        """Record a hit and raise :class:`HTTPException` if over the limit.

        The hit is recorded on the success path only. A flood of
        denied requests is intentionally NOT counted against the
        bucket so an attacker can't keep the bucket near-full by
        sending rejected requests.
        """
        limit = self.limit_for(role=role)
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            bucket = self._buckets[user_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise _too_many_requests()
            bucket.append(now)

    def reset(self) -> None:
        """Drop all bucket state.

        Test-only helper; never call in production.
        """
        self._buckets.clear()


# ---------------------------------------------------------------------------
# Redis sliding-window limiter (Slice 9a)
# ---------------------------------------------------------------------------


# Atomic sliding-window script.
#
#   KEYS[1] = sorted-set key for the user_id's bucket
#   ARGV[1] = window cutoff (now - window_seconds), float
#   ARGV[2] = unique member id
#   ARGV[3] = now (epoch seconds, float), used as the ZSET score
#   ARGV[4] = limit (per-window hit cap for this role)
#   ARGV[5] = bucket TTL in seconds (window_seconds + 1)
#
# Returns: ``{allowed:int, count:int}`` where ``allowed`` is 1 if the
# hit was recorded and 0 if it was rejected. The count returned is
# the post-decision size of the bucket (so the caller can surface
# rate-limit headers in a future slice).
#
# The script is *atomic* on the Redis server — no other client's
# commands can interleave between the ZREMRANGEBYSCORE and the
# conditional ZADD, so two uvicorn workers cannot both observe
# count == limit-1 and both succeed.
#
# The ZADD is guarded by the limit so a flood of 429-rejected
# requests does not pin the bucket: denied requests are never
# inserted, and the bucket ages out naturally.
_SLIDING_WINDOW_LUA: str = """
local key = KEYS[1]
local cutoff = tonumber(ARGV[1])
local member = ARGV[2]
local now = tonumber(ARGV[3])
local limit = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
    return {0, count}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return {1, count + 1}
"""


class RedisRateLimiter:
    """Sliding-window rate limiter backed by a Redis sorted set.

    The bucket is one ``ZSET`` per ``user_id``. Members are unique
    strings (``"<epoch>:<uuid4>"``); scores are epoch seconds. The
    :data:`_SLIDING_WINDOW_LUA` script atomically evicts expired
    members, decides whether the new hit fits under the limit, and
    inserts the hit only on the success path. See the script's
    docstring for the contract.

    Limits are read from :attr:`Settings.rate_limit_demo_user_per_hour`
    and :attr:`Settings.rate_limit_admin_per_hour` at construction
    time, so operator-tunable env vars are honoured.

    The Redis client is created lazily by :mod:`app.core.redis_client`
    from :attr:`Settings.redis_url`. Production deploys MUST set that
    env var.
    """

    def __init__(
        self,
        *,
        client: Redis,
        window_seconds: int,
        demo_user_per_window: int,
        admin_per_window: int,
        key_prefix: str,
    ) -> None:
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        if demo_user_per_window < 1 or admin_per_window < 1:
            raise ValueError("per-window limits must be >= 1")
        if not key_prefix:
            raise ValueError("key_prefix must be a non-empty string")
        self._client = client
        self._window_seconds = window_seconds
        self._limits: dict[str, int] = {
            "demo_user": demo_user_per_window,
            "admin": admin_per_window,
        }
        self._key_prefix = key_prefix.rstrip(":")
        # The script body is held as a string so we can call
        # ``client.eval()`` directly. ``register_script`` would use
        # EVALSHA first (which fakeredis does not support), so we
        # always EVAL — slightly more bytes on the wire for the
        # first call, but Lua scripts are small and the cost is
        # negligible compared to the round-trip itself.
        self._script_body = _SLIDING_WINDOW_LUA

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def _bucket_key(self, user_id: str) -> str:
        return f"{self._key_prefix}:{user_id}"

    def limit_for(self, *, role: str) -> int:
        return self._limits.get(role, self._limits["demo_user"])

    async def check(self, *, user_id: str, role: str) -> None:
        """Record a hit atomically and raise 429 if over the limit.

        The script does the eviction + decision + insert + expire in
        a single server-side step; the client awaits the result. If
        the script returns ``allowed == 0`` the hit is rejected and
        nothing is added to the bucket — a flood of rejected
        requests cannot pin a legitimate user out.
        """
        limit = self.limit_for(role=role)
        now = time.time()
        cutoff = now - self._window_seconds
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        key = self._bucket_key(user_id)
        allowed, _count = await self._client.eval(  # type: ignore[union-attr]
            self._script_body,
            1,  # number of KEYS
            key,
            cutoff,
            member,
            now,
            limit,
            self._window_seconds + 1,
        )
        if not int(allowed):
            raise _too_many_requests()


# ---------------------------------------------------------------------------
# Process-wide limiter
# ---------------------------------------------------------------------------


def _too_many_requests() -> Exception:
    """Build a 429 :class:`HTTPException` carrying the standard error envelope."""
    request_id = get_current_request_id() or ""
    return error_response(
        request_id=request_id,
        code=APIErrorCode.rate_limited,
        message=(
            "Rate limit exceeded. The demo allows a small number of "
            "queries per hour per user; try again later."
        ),
    )


# Process-wide singleton. The implementation chosen at first use
# stays until :func:`reset_limiter` is called (test-only).
_limiter: RateLimiter | RedisRateLimiter | None = None


def _build_limiter(settings: Settings) -> RateLimiter | RedisRateLimiter:
    """Construct the limiter that matches the current settings."""
    if settings.redis_url:
        from app.core.redis_client import get_redis_client

        return RedisRateLimiter(
            client=get_redis_client(),
            window_seconds=settings.rate_limit_window_seconds,
            demo_user_per_window=settings.rate_limit_demo_user_per_hour,
            admin_per_window=settings.rate_limit_admin_per_hour,
            key_prefix=settings.redis_key_prefix,
        )
    return RateLimiter(
        window_seconds=settings.rate_limit_window_seconds,
        demo_user_per_window=settings.rate_limit_demo_user_per_hour,
        admin_per_window=settings.rate_limit_admin_per_hour,
    )


def get_limiter(settings: Settings) -> _LimiterLike:
    """Return the process-wide rate limiter, building it lazily.

    The limiter is rebuilt when the operator-tunable settings
    (window length, per-role limits, redis URL) change so a config
    reload after startup picks up the new values. The rebuild is
    cheap; the limiter holds no persistent state on the server.
    """
    global _limiter
    if _limiter is not None and _settings_match(_limiter, settings):
        return _limiter
    _limiter = _build_limiter(settings)
    return _limiter


def _settings_match(limiter: _LimiterLike, settings: Settings) -> bool:
    """Return True if the cached limiter was built from the same settings.

    We only check the fields the limiter's construction consumed; a
    redis URL rotation is also handled by :mod:`app.core.redis_client`
    (the redis client itself resets when its URL changes).
    """
    return (
        limiter.window_seconds == settings.rate_limit_window_seconds
        and limiter.limit_for(role="demo_user") == settings.rate_limit_demo_user_per_hour
        and limiter.limit_for(role="admin") == settings.rate_limit_admin_per_hour
    )


def reset_limiter() -> None:
    """Drop the process-wide limiter (test-only)."""
    global _limiter
    _limiter = None


async def enforce_rate_limit(
    *,
    user_id: str,
    role: str,
    settings: Settings,
) -> None:
    """Apply the rate limit for an authenticated request.

    Routes that already use :func:`require_demo_api_key` (which
    returns the user id string) call this directly, or — preferred
    — chain the :func:`rate_limited_demo` / :func:`rate_limited_admin`
    dependency so the limit is enforced uniformly across all
    authenticated routes.

    The function raises the standard envelope on overflow; the caller
    does not need to do anything special.
    """
    if not settings.rate_limit_enabled:
        return
    limiter = get_limiter(settings)
    await limiter.check(user_id=user_id, role=role)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
#
# Chained dependencies that wrap :func:`require_demo_api_key` /
# :func:`require_admin_api_key` with the rate limit. Routes add
# ``Depends(rate_limited_demo)`` instead of ``Depends(require_demo_api_key)``
# so the limit is enforced uniformly. A new authenticated route that
# forgets to add the dependency is caught by the route test suite,
# which asserts the dependency is in place.
#
# The dependency returns the same ``user_id`` string the auth
# dependency returns, so existing route signatures are unchanged
# (they replace ``require_demo_api_key`` with ``rate_limited_demo``).


async def rate_limited_demo(
    user_id: Annotated[str, Depends(require_demo_api_key)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Demo-user auth + rate limit. Returns the demo user id."""
    await enforce_rate_limit(user_id=user_id, role="demo_user", settings=settings)
    return user_id


async def rate_limited_admin(
    user_id: Annotated[str, Depends(require_admin_api_key)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Admin auth + rate limit. Returns the admin user id."""
    await enforce_rate_limit(user_id=user_id, role="admin", settings=settings)
    return user_id


__all__ = [
    "RateLimiter",
    "RedisRateLimiter",
    "enforce_rate_limit",
    "get_limiter",
    "rate_limited_admin",
    "rate_limited_demo",
    "reset_limiter",
]
