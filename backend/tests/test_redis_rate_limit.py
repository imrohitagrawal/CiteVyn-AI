"""Tests for the Slice 9a Redis sliding-window rate limiter.

Uses :mod:`fakeredis.aioredis` so the suite remains hermetic — no
external Redis service required. Verifies the core contract: the
limiter records a hit, accepts up to ``limit`` hits in the window,
and rejects the ``limit + 1``-th hit with the standard error
envelope.
"""

from __future__ import annotations

import pytest

from app.core import rate_limit


@pytest.fixture
def fake_redis():
    """Yield a fakeredis async client and reset the rate-limit singletons."""
    import fakeredis.aioredis as fake_aioredis

    rate_limit.reset_limiter()
    client = fake_aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        rate_limit.reset_limiter()
        import asyncio

        asyncio.run(client.aclose())


async def test_redis_limiter_accepts_hits_under_limit(fake_redis) -> None:
    """A new user is allowed to make ``limit`` requests in a row."""
    limiter = rate_limit.RedisRateLimiter(
        client=fake_redis,
        window_seconds=60,
        demo_user_per_window=3,
        admin_per_window=10,
        key_prefix="citevyn:rl:test",
    )
    for _ in range(3):
        await limiter.check(user_id="alice", role="demo_user")


async def test_redis_limiter_rejects_overflow(fake_redis) -> None:
    """The ``limit + 1``-th hit raises the standard 429 envelope."""
    from fastapi import HTTPException

    from app.core.errors import APIErrorCode

    class _LowLimit(rate_limit.RedisRateLimiter):
        def limit_for(self, *, role: str) -> int:  # type: ignore[override]
            return 2

    limiter = _LowLimit(
        client=fake_redis,
        window_seconds=60,
        demo_user_per_window=2,
        admin_per_window=10,
        key_prefix="citevyn:rl:test",
    )
    await limiter.check(user_id="alice", role="demo_user")
    await limiter.check(user_id="alice", role="demo_user")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check(user_id="alice", role="demo_user")
    assert exc_info.value.status_code == 429
    assert APIErrorCode.rate_limited.value in str(exc_info.value.detail)


async def test_redis_limiter_isolates_users(fake_redis) -> None:
    """A second user has its own bucket and is not affected by the first user's overflow."""
    from fastapi import HTTPException

    class _LowLimit(rate_limit.RedisRateLimiter):
        def limit_for(self, *, role: str) -> int:  # type: ignore[override]
            return 1

    limiter = _LowLimit(
        client=fake_redis,
        window_seconds=60,
        demo_user_per_window=1,
        admin_per_window=10,
        key_prefix="citevyn:rl:test",
    )
    await limiter.check(user_id="alice", role="demo_user")
    with pytest.raises(HTTPException):
        await limiter.check(user_id="alice", role="demo_user")
    # Bob is untouched.
    await limiter.check(user_id="bob", role="demo_user")


async def test_get_limiter_returns_redis_when_url_set(fake_redis, monkeypatch) -> None:
    """``get_limiter`` returns the Redis implementation when ``redis_url`` is set."""
    from app.core import redis_client
    from app.core.config import Settings

    # Redirect the redis_client factory to return the fakeredis client
    # instead of opening a real connection. The factory is now
    # parameterless (URL is read from settings).
    monkeypatch.setattr(redis_client, "get_redis_client", lambda: fake_redis)
    rate_limit.reset_limiter()
    settings = Settings(redis_url="redis://localhost:6379/0")
    limiter = rate_limit.get_limiter(settings)
    assert isinstance(limiter, rate_limit.RedisRateLimiter)


async def test_get_limiter_returns_in_process_without_url() -> None:
    """Without ``redis_url`` the in-process :class:`RateLimiter` is returned."""
    from app.core.config import Settings

    rate_limit.reset_limiter()
    settings = Settings()
    limiter = rate_limit.get_limiter(settings)
    assert isinstance(limiter, rate_limit.RateLimiter)


def test_enforce_rate_limit_disabled_skips_check() -> None:
    """``rate_limit_enabled=False`` short-circuits before any check."""
    from app.core.config import Settings

    rate_limit.reset_limiter()
    settings = Settings(rate_limit_enabled=False)
    import asyncio

    # Should not raise even with a tight limit.
    asyncio.run(rate_limit.enforce_rate_limit(user_id="alice", role="demo_user", settings=settings))


def test_redis_limiter_rejects_empty_prefix() -> None:
    """A blank ``key_prefix`` raises — the prefix is a safety net for shared Redis."""
    import fakeredis.aioredis as fake_aioredis

    client = fake_aioredis.FakeRedis(decode_responses=True)
    import asyncio

    asyncio.run(client.aclose())
    with pytest.raises(ValueError, match="key_prefix"):
        rate_limit.RedisRateLimiter(
            client=client,
            window_seconds=60,
            demo_user_per_window=3,
            admin_per_window=10,
            key_prefix="",
        )
