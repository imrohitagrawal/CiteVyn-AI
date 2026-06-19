"""Seed the demo catalog.

Idempotent: existing rows are left untouched. Run from the repository
root with ``uv run python -m db.seed.seed_catalog`` after
``alembic upgrade head`` and ``uv run python -m db.seed.seed_users``.

The data shape mirrors ``backend/tests/conftest.py::seed_catalog`` so
the stub LLM returns a deterministic grounded answer on a seeded
question. The four product areas (``claude_api``, ``claude_code``,
``codex``, ``gemini_api``) match the exact-term retriever's demo
expectations and the Slice 7 test assertions.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Make the backend package importable when running as a script.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings  # noqa: E402
from app.models import (  # noqa: E402
    Chunk,
    Document,
    DocumentStatus,
    ExactTerm,
    IndexStatus,
    IndexVersion,
    TermType,
)

INDEX_VERSION: str = "v1"
SOURCE_VERSION_HASH: str = "sha256:demo-seed-v1"
SOURCE_NAME: str = "docs.test"


@dataclass(frozen=True)
class _DocDef:
    """One document + its primary chunk + optional exact term."""

    product_area: str
    title: str
    source_url: str
    heading: str
    chunk_text: str
    context_summary: str
    exact_term_text: str | None = None
    exact_term_type: TermType | None = None


# TermType values used by the seed. The conftest seeds the same
# corpus with the raw strings ``"env_var"`` and ``"cli_flag"``;
# those happen to work on SQLite (the column is ``String(32)``) but
# would fail Postgres enum coercion after migration
# ``0002_promote_strenum_to_native`` adds the native
# ``citevyn_term_type`` enum. The seed uses canonical ``TermType``
# values directly so it works on both backends.
_TERM_TYPE_MAP: dict[str, TermType] = {
    "env_var": TermType.environment_variable,
    "cli_flag": TermType.flag,
}

_DOC_DEFS: tuple[_DocDef, ...] = (
    _DocDef(
        product_area="claude_api",
        title="Claude API",
        source_url="https://docs.test/claude",
        heading="Rate limits",
        chunk_text=(
            "The Claude API enforces a rate limit of 50 requests per minute "
            "per API key. Set `X-API-Key` to authenticate."
        ),
        context_summary="Claude API rate limits",
        exact_term_text="CLAUDE_API_RATE_LIMIT",
        exact_term_type=_TERM_TYPE_MAP["env_var"],
    ),
    _DocDef(
        product_area="claude_code",
        title="Claude Code",
        source_url="https://docs.test/claude-code",
        heading="Permissions",
        chunk_text=(
            "Claude Code uses a permissions file. Configure with "
            "`claude-code configure` to allow or deny tools."
        ),
        context_summary="Claude Code permissions",
    ),
    _DocDef(
        product_area="codex",
        title="Codex",
        source_url="https://docs.test/codex",
        heading="Model flag",
        chunk_text=(
            "Use `codex --model gpt-4` to pick a model. The default is "
            "`gpt-3.5`. Environment variable OPENAI_API_KEY is required."
        ),
        context_summary="Codex model flag",
        exact_term_text="--model",
        exact_term_type=_TERM_TYPE_MAP["cli_flag"],
    ),
    _DocDef(
        product_area="gemini_api",
        title="Gemini API",
        source_url="https://docs.test/gemini",
        heading="Streaming",
        chunk_text=(
            "The Gemini API supports streaming responses. Send the request "
            "with stream=true to receive a stream of partial responses."
        ),
        context_summary="Gemini API streaming",
    ),
)


async def seed(database_url: str) -> dict[str, int]:
    """Insert the demo catalog into ``database_url``.

    Returns a tally of how many new rows were inserted per table; rows
    that already existed are not counted. The script is safe to re-run.
    """
    engine = create_async_engine(database_url, future=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    tally: dict[str, int] = {
        "index_versions": 0,
        "documents": 0,
        "chunks": 0,
        "exact_terms": 0,
    }
    async with sessionmaker() as session:
        # --- index version ---------------------------------------------
        existing_version = await session.scalar(
            select(IndexVersion).where(IndexVersion.index_version == INDEX_VERSION)
        )
        if existing_version is None:
            session.add(
                IndexVersion(
                    index_version=INDEX_VERSION,
                    status=IndexStatus.active,
                    source_version_hash=SOURCE_VERSION_HASH,
                    created_at=now,
                    promoted_at=now,
                )
            )
            await session.flush()
            tally["index_versions"] += 1

        for definition in _DOC_DEFS:
            # --- document ------------------------------------------------
            existing_doc = await session.scalar(
                select(Document).where(
                    Document.source_url == definition.source_url,
                    Document.index_version == INDEX_VERSION,
                )
            )
            if existing_doc is None:
                doc = Document(
                    document_id=uuid.uuid4(),
                    index_version=INDEX_VERSION,
                    source_name=SOURCE_NAME,
                    product_area=definition.product_area,
                    source_url=definition.source_url,
                    title=definition.title,
                    content_checksum=f"sha256:demo-{definition.product_area}",
                    status=DocumentStatus.active,
                    last_fetched_at=now,
                    last_indexed_at=now,
                )
                session.add(doc)
                await session.flush()
                tally["documents"] += 1
            else:
                doc = existing_doc

            # --- chunk ---------------------------------------------------
            existing_chunk = await session.scalar(
                select(Chunk).where(Chunk.document_id == doc.document_id)
            )
            if existing_chunk is None:
                chunk = Chunk(
                    chunk_id=uuid.uuid4(),
                    document_id=doc.document_id,
                    product_area=doc.product_area,
                    section_path="/section",
                    heading=definition.heading,
                    parent_heading=None,
                    chunk_text=definition.chunk_text,
                    context_summary=definition.context_summary,
                    chunk_order=1,
                    content_checksum=f"sha256:demo-chunk-{definition.product_area}",
                )
                session.add(chunk)
                await session.flush()
                tally["chunks"] += 1
            else:
                chunk = existing_chunk

            # --- exact term (optional) ----------------------------------
            if definition.exact_term_text is not None and definition.exact_term_type is not None:
                existing_term = await session.scalar(
                    select(ExactTerm).where(
                        ExactTerm.term_text == definition.exact_term_text,
                        ExactTerm.product_area == definition.product_area,
                        ExactTerm.chunk_id == chunk.chunk_id,
                    )
                )
                if existing_term is None:
                    session.add(
                        ExactTerm(
                            term_id=uuid.uuid4(),
                            term_text=definition.exact_term_text,
                            term_type=definition.exact_term_type,
                            product_area=definition.product_area,
                            document_id=doc.document_id,
                            chunk_id=chunk.chunk_id,
                        )
                    )
                    tally["exact_terms"] += 1

        await session.commit()
    await engine.dispose()
    return tally


def main() -> None:
    """CLI entry point: seed and print a one-line summary."""
    settings = get_settings()
    tally = asyncio.run(seed(settings.database_url))
    print(
        f"Seeded catalog into {settings.database_url}: "
        f"index_versions=+{tally['index_versions']} "
        f"documents=+{tally['documents']} "
        f"chunks=+{tally['chunks']} "
        f"exact_terms=+{tally['exact_terms']}"
    )


if __name__ == "__main__":
    main()
