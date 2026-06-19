"""Slice 8: tests for the in-process :class:`RateLimiter`.

The tests are pure unit tests (no FastAPI, no DB) so they cover the
sliding-window logic in isolation. Route-level integration with
:class:`enforce_rate_limit` is exercised by the route tests.
"""

from __future__ import annotations

import pytest

from app.core.errors import APIErrorCode
from app.core.rate_limit import (
    DEFAULT_LIMIT_DEMO_USER,
    RateLimiter,
)


@pytest.fixture
def limiter() -> RateLimiter:
    """A 1-second window so eviction is testable in real time."""
    return RateLimiter(window_seconds=1)


async def test_first_hit_is_allowed(limiter: RateLimiter) -> None:
    """A fresh bucket accepts the first call."""
    await limiter.check(user_id="u1", role="demo_user")


async def test_within_window_hits_are_allowed(limiter: RateLimiter) -> None:
    """A few hits within the window are all allowed."""
    for _ in range(5):
        await limiter.check(user_id="u1", role="demo_user")


async def test_overflow_raises_envelope(limiter: RateLimiter) -> None:
    """The ``demo_user`` limit (30) is enforced; the 31st call raises."""
    user = "u1"
    for _ in range(DEFAULT_LIMIT_DEMO_USER):
        await limiter.check(user_id=user, role="demo_user")
    with pytest.raises(Exception) as exc_info:
        await limiter.check(user_id=user, role="demo_user")
    # The exception carries the standard error envelope.
    assert exc_info.value.status_code == 429  # type: ignore[attr-defined]
    assert exc_info.value.detail["error"]["code"] == APIErrorCode.rate_limited.value  # type: ignore[attr-defined]


async def test_admin_limit_is_higher(limiter: RateLimiter) -> None:
    """An admin can exceed the demo-user limit up to the admin limit."""
    user = "u_admin"
    # Fill to demo_user limit; the next call should still be allowed because the
    # user's role is "admin".
    for _ in range(DEFAULT_LIMIT_DEMO_USER):
        await limiter.check(user_id=user, role="admin")
    # One more — the bucket is now at the demo-user cap, which is < admin limit.
    await limiter.check(user_id=user, role="admin")


async def test_eviction_after_window_expires(limiter: RateLimiter) -> None:
    """Hits outside the window are evicted and the bucket accepts new calls."""
    import asyncio

    user = "u1"
    # Fill the bucket to the limit.
    for _ in range(DEFAULT_LIMIT_DEMO_USER):
        await limiter.check(user_id=user, role="demo_user")
    with pytest.raises(Exception):
        await limiter.check(user_id=user, role="demo_user")
    # Wait for the window to elapse (1.1s to avoid the boundary).
    await asyncio.sleep(1.1)
    # After the window, the bucket is empty and the next call succeeds.
    await limiter.check(user_id=user, role="demo_user")


async def test_different_users_have_separate_buckets(limiter: RateLimiter) -> None:
    """User A's overflow does not affect user B's bucket."""
    for _ in range(DEFAULT_LIMIT_DEMO_USER):
        await limiter.check(user_id="alice", role="demo_user")
    with pytest.raises(Exception):
        await limiter.check(user_id="alice", role="demo_user")
    # Bob has his own bucket.
    await limiter.check(user_id="bob", role="demo_user")


async def test_overflow_does_not_record_hit(limiter: RateLimiter) -> None:
    """An overflowed call does NOT add a timestamp to the bucket.

    Without this, an attacker could keep the bucket full by sending
    rejected requests in a tight loop, extending the time until the
    user can send a legitimate one.
    """
    user = "u1"
    for _ in range(DEFAULT_LIMIT_DEMO_USER):
        await limiter.check(user_id=user, role="demo_user")
    # Several overflowed calls.
    for _ in range(5):
        with pytest.raises(Exception):
            await limiter.check(user_id=user, role="demo_user")
    # The bucket still has exactly the original count, so eviction
    # after the window elapses leaves a fresh bucket.
    assert len(limiter._buckets[user]) == DEFAULT_LIMIT_DEMO_USER  # noqa: SLF001 (test introspection)


async def test_unknown_role_falls_back_to_demo_user(limiter: RateLimiter) -> None:
    """An unknown role is treated as the demo-user limit (fail-closed)."""
    user = "u1"
    for _ in range(DEFAULT_LIMIT_DEMO_USER):
        await limiter.check(user_id=user, role="mystery_role")
    with pytest.raises(Exception):
        await limiter.check(user_id=user, role="mystery_role")


def test_zero_window_seconds_rejected() -> None:
    """A non-positive window is invalid — sliding windows need a width."""
    with pytest.raises(ValueError):
        RateLimiter(window_seconds=0)
