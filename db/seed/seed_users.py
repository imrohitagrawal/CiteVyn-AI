"""Seed the two MVP users.

Idempotent: existing rows are left untouched. Run from the repository
root with ``uv run python -m db.seed.seed_users`` after
``alembic upgrade head``.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Make the backend package importable when running as a script.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models import User, UserRole  # noqa: E402

DEFAULT_USERS: tuple[tuple[str, UserRole], ...] = (
    ("demo_user", UserRole.demo_user),
    ("admin", UserRole.admin),
)


async def seed(database_url: str) -> None:
    engine = create_async_engine(database_url, future=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with sessionmaker() as session:  # type: AsyncSession
        for user_id, role in DEFAULT_USERS:
            existing = await session.scalar(
                select(User).where(User.user_id == user_id)
            )
            if existing is not None:
                continue
            session.add(User(user_id=user_id, role=role, created_at=now))
        await session.commit()
    await engine.dispose()


def main() -> None:
    settings = get_settings()
    asyncio.run(seed(settings.database_url))
    print(f"Seeded {len(DEFAULT_USERS)} users into {settings.database_url}.")


if __name__ == "__main__":
    main()
