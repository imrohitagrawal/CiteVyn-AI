"""Console-script entry point for the ingestion worker.

Usage:

    citevyn-worker run                       # ingest all MVP sources
    citevyn-worker run --source codex        # ingest one source
    citevyn-worker run --index-version v-test
    citevyn-worker list-sources

The CLI is intentionally thin: it builds a single
:class:`IngestionRunner` and drives it through one source
or all of them. Polling, retries, and parallel workers are
deliberately out of scope for the MVP — the admin
``POST /v1/admin/index_versions/{version}/promote`` is
the only way to ship a build, and that gate is gated
behind the admin API key.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import get_sessionmaker
from app.core.logging import configure_logging
from app.worker.allowlist import MVP_SOURCES, SourceSpec, get_source, list_source_names
from app.worker.embedder import build_embedder
from app.worker.fetchers import build_fetcher
from app.worker.runner import IngestionRunner, RunResult, ensure_index_version

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    configure_logging()
    if args.command == "list-sources":
        return _cmd_list_sources()
    if args.command == "run":
        return _cmd_run(args)
    parser.print_help()
    return 1


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _cmd_list_sources() -> int:
    """Print the MVP source list and exit 0."""
    for name in list_source_names():
        spec = get_source(name)
        print(f"{spec.name}\t{spec.product_area}\t{spec.fetcher}\t{spec.location}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Ingest all sources (or the one named by ``--source``)."""
    settings = get_settings()
    runner = _build_runner(settings)
    sessionmaker = get_sessionmaker()
    sources = _resolve_sources(args.source)
    return asyncio.run(_drive(runner, sessionmaker, sources, args.index_version))


async def _drive(
    runner: IngestionRunner,
    sessionmaker: async_sessionmaker[AsyncSession],
    sources: list[SourceSpec],
    index_version: str,
) -> int:
    """Drive ``runner`` through ``sources`` and report."""
    failed = 0
    async with sessionmaker() as session:
        # One IndexVersion row for the whole run. Idempotent
        # — a re-run for the same ``index_version`` returns
        # the existing row.
        await ensure_index_version(
            session,
            index_version=index_version,
            source_version_hash=runner.source_version_hash,
        )
        await session.commit()

    for source in sources:
        async with sessionmaker() as session:
            result = await runner.run(session, source=source)
        _print_result(result)
        if result.status.value == "failed":
            failed += 1
    return 0 if failed == 0 else 2


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="citevyn-worker",
        description="Ingestion worker (Slice 8 step 6).",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list-sources", help="Print the MVP source list.")

    run = sub.add_parser("run", help="Ingest one source or all sources.")
    run.add_argument(
        "--source",
        default=None,
        help="Ingest one source by name (default: all MVP sources).",
    )
    run.add_argument(
        "--index-version",
        default="v-local",
        help="IndexVersion key to write to (default: v-local).",
    )
    return parser


def _build_runner(settings: Settings) -> IngestionRunner:
    """Build the runner with the default fetcher + embedder."""
    fetcher = build_fetcher(_pick_first_source())  # build default-root LocalFetcher
    embedder = build_embedder()
    return IngestionRunner(
        fetcher=fetcher,
        embedder=embedder,
        source_version_hash=settings.source_version_hash,
        index_version="v-local",
    )


def _pick_first_source() -> SourceSpec:
    """Return the first :class:`SourceSpec` (a placeholder for fetcher build)."""
    return MVP_SOURCES[0]


def _resolve_sources(name: str | None) -> list[SourceSpec]:
    """Return the source list — either one source by name or all of them."""
    if name is None:
        return list(MVP_SOURCES)
    return [get_source(name)]


def _print_result(result: RunResult) -> None:
    """Print a one-line summary of ``result`` to stderr."""
    if result.status.value == "completed":
        logger.info(
            "ingestion completed source=%s chunks=%d terms=%d",
            result.source_name,
            result.chunk_count,
            result.term_count,
        )
    else:
        logger.error(
            "ingestion failed source=%s error_type=%s message=%s",
            result.source_name,
            result.error_type,
            result.error_message,
        )


if __name__ == "__main__":
    raise SystemExit(main())
