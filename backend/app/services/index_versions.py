"""Service layer for :class:`app.models.index_versions.IndexVersion`.

Read paths (``list_versions``, ``get_version``) and the only write
path the HTTP surface exposes today: :func:`promote_version`.

Design notes
------------
* The route layer is the only place this is called from; the
  worker (Step 6) writes :class:`IndexVersion` rows directly via
  the ORM during a build.
* :func:`promote_version` is transactional. The release plan
  requires "last known good" is preserved, so a promotion moves
  the current ``active`` row to ``previous_good`` and the
  chosen candidate to ``active`` in the same transaction. A
  second caller racing with the first will lose (one wins, the
  other sees a clean state) — the function does not retry.
* Promote is idempotent on the same target. If ``index_version``
  is already ``active``, the call returns without writing and
  without raising.
* Promote is a privileged write. Every call writes one
  :class:`AuditEvent` row (``promote_index``) inside the same
  transaction so the audit log and the data move together.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction, IndexStatus
from app.models.index_versions import IndexVersion
from app.services import audit as audit_service


async def list_versions(
    session: AsyncSession,
    *,
    status: IndexStatus | None = None,
) -> list[IndexVersion]:
    """Return all index versions, optionally filtered by ``status``.

    Sorted by ``created_at`` ascending so the seed row appears
    before any later candidates in the admin UI. ``None`` when no
    rows match — the route layer turns that into an empty list.
    """
    stmt = select(IndexVersion)
    if status is not None:
        stmt = stmt.where(IndexVersion.status == status)
    stmt = stmt.order_by(IndexVersion.created_at.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_version(
    session: AsyncSession,
    *,
    index_version: str,
) -> IndexVersion | None:
    """Return the row keyed by ``index_version`` or ``None``."""
    return await session.get(IndexVersion, index_version)


async def count_documents_for_version(
    session: AsyncSession,
    *,
    index_version: str,
) -> int:
    """Count documents attached to ``index_version``.

    Used by the admin detail endpoint to show "active is 12 docs
    / 348 chunks" without re-iterating the relationship. Lives
    here (not in the route) so the service is the single source
    of truth for what "index state" means.
    """
    from app.models.documents import Document

    stmt = select(func.count()).select_from(Document).where(Document.index_version == index_version)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def promote_version(
    session: AsyncSession,
    *,
    index_version: str,
    admin_user_id: str,
    request_id: str,
) -> IndexVersion:
    """Promote ``index_version`` to :data:`IndexStatus.active`.

    Steps inside a single transaction:

    1. Lock the target row (``SELECT ... FOR UPDATE``); 404 if
       not found.
    2. If the target is already ``active``, return it unchanged
       and skip steps 3-4 (idempotent on the same target).
    3. Move the current ``active`` row to ``previous_good``.
       If no row is currently ``active``, step 3 is a no-op.
    4. Mark the target ``active`` and stamp ``promoted_at`` with
       the current UTC instant.
    5. Append an ``AuditEvent`` row with action ``promote_index``
       so the change shows up in the audit log with the same
       request id the caller has on their HTTP response.

    Returns the (now-active) target row. The caller is
    responsible for committing the session.
    """
    now = datetime.now(UTC)

    target = (
        await session.execute(
            select(IndexVersion)
            .where(IndexVersion.index_version == index_version)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if target is None:
        raise _IndexVersionNotFound(index_version)

    if target.status is IndexStatus.active:
        # Idempotent: target is already active. Do not write an
        # audit row — the state didn't change.
        return target

    # Find the current active row (if any) and demote it. We do
    # not take a row-level lock on the demotion candidate; the
    # promotion is a single-step read+update and the
    # ``active`` status is logically a singleton.
    current_active = (
        await session.execute(
            select(IndexVersion).where(IndexVersion.status == IndexStatus.active).with_for_update()
        )
    ).scalar_one_or_none()
    if current_active is not None and current_active.index_version != target.index_version:
        current_active.status = IndexStatus.previous_good

    target.status = IndexStatus.active
    target.promoted_at = now

    await audit_service.record_admin_action(
        session,
        admin_user_id=admin_user_id,
        action=AuditAction.promote_index,
        resource_type="index_version",
        resource_id=target.index_version,
        extra={
            "request_id": request_id,
            "promoted_at": now.isoformat(),
        },
    )
    return target


class _IndexVersionNotFound(Exception):
    """Raised by :func:`promote_version` when the target row is missing.

    Not the standard :class:`APIErrorCode`-shaped envelope — the
    route layer catches this and turns it into a 404.
    """

    def __init__(self, index_version: str) -> None:
        self.index_version = index_version
        super().__init__(f"index_version not found: {index_version}")


__all__ = [
    "IndexVersionNotFound",
    "count_documents_for_version",
    "get_version",
    "list_versions",
    "promote_version",
]


# Re-export the private error under the public name so callers
# don't have to reach for the underscore prefix.
IndexVersionNotFound = _IndexVersionNotFound
