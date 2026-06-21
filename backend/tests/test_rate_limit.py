"""Slice 8: tests for the in-process :class:`RateLimiter`.

The tests are pure unit tests (no FastAPI, no DB) so they cover the
sliding-window logic in isolation. Route-level integration with
:class:`enforce_rate_limit` is exercised by the route tests.

The :class:`RateLimiter` now takes ``demo_user_per_window`` and
``admin_per_window`` (from :class:`Settings.rate_limit_*_per_hour`),
so the fixture wires small values that fit the eviction test. The
``LIMIT`` constant is the value the fixture uses for the demo-user
cap; tests assert against that constant instead of an import.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.errors import APIErrorCode
from app.core.rate_limit import RateLimiter

# Small cap so the overflow tests stay fast and the concurrent-burst
# test doesn't spawn 60 coroutines just to fill the bucket.
LIMIT: int = 5
ADMIN_LIMIT: int = 10


@pytest.fixture
def limiter() -> RateLimiter:
    """A 1-second window so eviction is testable in real time."""
    return RateLimiter(
        window_seconds=1,
        demo_user_per_window=LIMIT,
        admin_per_window=ADMIN_LIMIT,
    )


async def test_first_hit_is_allowed(limiter: RateLimiter) -> None:
    """A fresh bucket accepts the first call."""
    await limiter.check(user_id="u1", role="demo_user")


async def test_within_window_hits_are_allowed(limiter: RateLimiter) -> None:
    """A few hits within the window are all allowed."""
    for _ in range(3):
        await limiter.check(user_id="u1", role="demo_user")


async def test_overflow_raises_envelope(limiter: RateLimiter) -> None:
    """The ``demo_user`` limit is enforced; the next call raises 429."""
    user = "u1"
    for _ in range(LIMIT):
        await limiter.check(user_id=user, role="demo_user")
    with pytest.raises(Exception) as exc_info:
        await limiter.check(user_id=user, role="demo_user")
    # The exception carries the standard error envelope.
    assert exc_info.value.status_code == 429  # type: ignore[attr-defined]
    assert exc_info.value.detail["error"]["code"] == APIErrorCode.rate_limited.value  # type: ignore[attr-defined]


async def test_admin_limit_is_higher(limiter: RateLimiter) -> None:
    """An admin can exceed the demo-user limit up to the admin limit."""
    user = "u_admin"
    # Fill to the demo-user limit.
    for _ in range(LIMIT):
        await limiter.check(user_id=user, role="admin")
    # More calls still allowed because role is "admin" and admin
    # cap is higher.
    for _ in range(ADMIN_LIMIT - LIMIT):
        await limiter.check(user_id=user, role="admin")


async def test_eviction_after_window_expires(limiter: RateLimiter) -> None:
    """Hits outside the window are evicted and the bucket accepts new calls."""
    import asyncio

    user = "u1"
    # Fill the bucket to the limit.
    for _ in range(LIMIT):
        await limiter.check(user_id=user, role="demo_user")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check(user_id=user, role="demo_user")
    assert exc_info.value.status_code == 429
    # Wait for the window to elapse (1.1s to avoid the boundary).
    await asyncio.sleep(1.1)
    # After the window, the bucket is empty and the next call succeeds.
    await limiter.check(user_id=user, role="demo_user")


async def test_different_users_have_separate_buckets(limiter: RateLimiter) -> None:
    """User A's overflow does not affect user B's bucket."""
    for _ in range(LIMIT):
        await limiter.check(user_id="alice", role="demo_user")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check(user_id="alice", role="demo_user")
    assert exc_info.value.status_code == 429
    # Bob has his own bucket.
    await limiter.check(user_id="bob", role="demo_user")


async def test_overflow_does_not_record_hit(limiter: RateLimiter) -> None:
    """An overflowed call does NOT add a timestamp to the bucket.

    Without this, an attacker could keep the bucket full by sending
    rejected requests in a tight loop, extending the time until the
    user can send a legitimate one.
    """
    user = "u1"
    for _ in range(LIMIT):
        await limiter.check(user_id=user, role="demo_user")
    # Several overflowed calls.
    for _ in range(5):
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check(user_id=user, role="demo_user")
        assert exc_info.value.status_code == 429
    # The bucket still has exactly the original count, so eviction
    # after the window elapses leaves a fresh bucket.
    assert len(limiter._buckets[user]) == LIMIT  # noqa: SLF001 (test introspection)


async def test_unknown_role_falls_back_to_demo_user(limiter: RateLimiter) -> None:
    """An unknown role is treated as the demo-user limit (fail-closed)."""
    user = "u1"
    for _ in range(LIMIT):
        await limiter.check(user_id=user, role="mystery_role")
    with pytest.raises(HTTPException) as exc_info:
        await limiter.check(user_id=user, role="mystery_role")
    assert exc_info.value.status_code == 429


def test_zero_window_seconds_rejected() -> None:
    """A non-positive window is invalid — sliding windows need a width."""
    with pytest.raises(ValueError):
        RateLimiter(
            window_seconds=0,
            demo_user_per_window=LIMIT,
            admin_per_window=ADMIN_LIMIT,
        )


def test_negative_window_seconds_rejected() -> None:
    """A negative window is invalid for the same reason as zero."""
    with pytest.raises(ValueError):
        RateLimiter(
            window_seconds=-1,
            demo_user_per_window=LIMIT,
            admin_per_window=ADMIN_LIMIT,
        )


def test_zero_demo_user_per_window_rejected() -> None:
    """A zero per-window limit would disable the limiter — reject it."""
    with pytest.raises(ValueError):
        RateLimiter(
            window_seconds=60,
            demo_user_per_window=0,
            admin_per_window=ADMIN_LIMIT,
        )


def test_zero_admin_per_window_rejected() -> None:
    """Same as above, for the admin cap."""
    with pytest.raises(ValueError):
        RateLimiter(
            window_seconds=60,
            demo_user_per_window=LIMIT,
            admin_per_window=0,
        )


async def test_concurrent_hits_do_not_burst_the_limit() -> None:
    """``2 * limit`` concurrent hits must still let only ``limit`` through.

    The implementation guards bucket mutation with an
    :class:`asyncio.Lock`. A regression that drops the lock
    (e.g. a future "optimisation") would let bursts slip
    through — this test pins the contract.
    """
    import asyncio

    # Use a longer window so the burst finishes well before the
    # 1-second fixture window expires.
    limiter = RateLimiter(
        window_seconds=60,
        demo_user_per_window=LIMIT,
        admin_per_window=ADMIN_LIMIT,
    )

    async def hit() -> bool:
        try:
            await limiter.check(user_id="concurrent_user", role="demo_user")
            return True
        except Exception:
            return False

    results = await asyncio.gather(*(hit() for _ in range(2 * LIMIT)))
    accepted = sum(1 for ok in results if ok)
    rejected = sum(1 for ok in results if not ok)
    assert accepted == LIMIT, f"expected exactly {LIMIT} accepted, got {accepted}"
    assert rejected == LIMIT, f"expected exactly {LIMIT} rejected, got {rejected}"
