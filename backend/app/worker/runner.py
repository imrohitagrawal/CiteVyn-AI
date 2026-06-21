"""Ingestion runner.

Drives one :class:`SourceSpec` through the full pipeline:

    fetch → parse → chunk → exact-terms → embed → persist

and writes an :class:`IngestionJob` row at the start and
end so the admin route can show progress.

Design notes
------------
* The runner is synchronous. The MVP CLI runs one source at
  a time and the per-source work is bounded (one local
  read + ~10 chunks). Step 7+ adds a queue and parallel
  workers.
* The runner owns the transaction. A successful run
  commits; any exception in any stage rolls back and the
  job row is marked ``failed``. The job's ``error_type``
  is the exception's class name (e.g. ``FetchError``,
  ``ParseError``); ``error_message`` is ``str(exc)``.
* The pipeline returns a :class:`RunResult` so the CLI can
  report what happened without re-querying.
* Idempotency: re-running the same source reuses the
  existing :class:`Document` row (if any) and replaces the
  chunks. The :class:`IngestionJob.source_version_hash`
  captures the "what version of the docs did we ingest?"
  signal; if it changes, the admin promote flow is the
  gate (a fresh :class:`IndexVersion` with the new hash).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunks import Chunk
from app.models.documents import Document
from app.models.enums import (
    DocumentStatus,
    IndexStatus,
    JobStage,
    JobStatus,
)
from app.models.exact_terms import ExactTerm
from app.models.index_versions import IndexVersion
from app.models.ingestion_jobs import IngestionJob
from app.worker.allowlist import SourceSpec
from app.worker.chunker import ChunkDraft, chunk_document
from app.worker.embedder import Embedder
from app.worker.exact_terms import extract_terms
from app.worker.fetchers import Fetcher, FetchError  # noqa: F401  re-export
from app.worker.parser import ParseError, parse_markdown  # noqa: F401  re-export


@dataclass(frozen=True)
class RunResult:
    """The outcome of one ingestion run.

    ``document_id`` is ``None`` if the run failed before
    the ``persist`` stage. ``chunk_count`` and
    ``term_count`` are the number of rows persisted; for a
    failed run they are 0.
    """

    job_id: uuid.UUID
    source_name: str
    status: JobStatus
    document_id: uuid.UUID | None = None
    chunk_count: int = 0
    term_count: int = 0
    error_type: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class IngestionRunner:
    """Run one source through the full pipeline.

    The runner is constructed once at boot and re-used.
    Tests construct a fresh runner per test with a custom
    :class:`Fetcher` (e.g. one that returns a synthetic
    document).
    """

    def __init__(
        self,
        *,
        fetcher: Fetcher,
        embedder: Embedder,
        source_version_hash: str = "sha256:mvp-snapshot-1",
        index_version: str = "v-local",
    ) -> None:
        """Create a runner with explicit collaborators.

        ``source_version_hash`` is the "what snapshot are we
        building against?" fingerprint. ``index_version`` is
        the key the runner writes to. The CLI defaults are
        good for the MVP; production swaps them for real
        values from the operator-issued source feed.
        """
        self._fetcher = fetcher
        self._embedder = embedder
        self._source_version_hash = source_version_hash
        self._index_version = index_version

    @property
    def source_version_hash(self) -> str:
        """Public read-only view of the snapshot hash (CLI / tests use this)."""
        return self._source_version_hash

    async def run(
        self,
        session: AsyncSession,
        *,
        source: SourceSpec,
    ) -> RunResult:
        """Ingest ``source`` end-to-end.

        Returns a :class:`RunResult` describing what
        happened. The function always writes a single
        :class:`IngestionJob` row (status ``completed`` or
        ``failed``); it does not write an ``IngestionJob``
        for a run that could not even start.
        """
        job = self._create_job(session, source=source)
        await session.flush()
        job_id = job.job_id

        try:
            self._set_stage(session, job, JobStage.fetching)
            raw = self._fetcher.fetch(source)
            await session.flush()

            self._set_stage(session, job, JobStage.parsing)
            parsed = parse_markdown(raw)
            await session.flush()

            self._set_stage(session, job, JobStage.chunking)
            drafts = chunk_document(parsed, source=source)
            await session.flush()

            self._set_stage(session, job, JobStage.embedding)
            chunks = await self._materialize_chunks(session, source=source, drafts=drafts)
            await session.flush()

            self._set_stage(session, job, JobStage.indexing)
            terms = await self._materialize_terms(session, source=source, chunks=chunks)
            self._mark_completed(session, job=job)
            await session.commit()

            return RunResult(
                job_id=job_id,
                source_name=source.name,
                status=JobStatus.completed,
                document_id=chunks[0].document_id if chunks else None,
                chunk_count=len(chunks),
                term_count=len(terms),
            )
        except Exception as exc:
            await session.rollback()
            self._mark_failed(session, job=job, error_type=type(exc).__name__, message=str(exc))
            await session.commit()
            return RunResult(
                job_id=job_id,
                source_name=source.name,
                status=JobStatus.failed,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    # -- internals -------------------------------------------------------

    def _create_job(
        self,
        session: AsyncSession,
        *,
        source: SourceSpec,
    ) -> IngestionJob:
        """Create the :class:`IngestionJob` row at status ``pending``."""
        now = datetime.now(UTC)
        job = IngestionJob(
            source_name=source.name,
            status=JobStatus.pending,
            stage=JobStage.fetching,
            started_at=now,
            completed_at=None,
            error_type=None,
            error_message=None,
            retryable=False,
        )
        session.add(job)
        return job

    def _set_stage(
        self,
        session: AsyncSession,
        job: IngestionJob,
        stage: JobStage,
    ) -> None:
        """Advance ``job`` to ``JobStatus.running`` + ``stage``.

        The job's ``status`` field is set to ``running``
        exactly once — at the first stage transition. The
        :func:`_mark_failed` helper is the only other
        writer to ``status``.
        """
        if job.status is JobStatus.pending:
            job.status = JobStatus.running
        job.stage = stage

    def _mark_failed(
        self,
        session: AsyncSession,
        *,
        job: IngestionJob,
        error_type: str,
        message: str,
    ) -> None:
        """Stamp ``job`` as failed with the error type and message.

        Called from the exception handler in :meth:`run`.
        The function does not commit — the caller does.

        After the rollback in :meth:`run` the :class:`IngestionJob`
        was evicted from the session, so we re-add it before
        committing the failure row. Re-adding a detached object
        with an existing PK triggers an UPDATE, not an INSERT —
        which is what we want (the rollback removed the
        ``INSERT``).
        """
        if job not in session:
            session.add(job)
        job.status = JobStatus.failed
        job.stage = JobStage.indexing  # last stage attempted
        job.completed_at = datetime.now(UTC)
        job.error_type = error_type
        job.error_message = message
        job.retryable = False  # MVP: no auto-retry; future: type-driven

    def _mark_completed(
        self,
        session: AsyncSession,
        *,
        job: IngestionJob,
    ) -> None:
        """Stamp ``job`` as completed at the end of the happy path.

        Same session lifecycle as :meth:`_mark_failed` — by
        the time this runs the session has flushed but not
        committed, so the object is still in the session and
        no re-add is needed.
        """
        job.status = JobStatus.completed
        job.stage = JobStage.indexing
        job.completed_at = datetime.now(UTC)
        job.error_type = None
        job.error_message = None
        job.retryable = False

    async def _materialize_chunks(
        self,
        session: AsyncSession,
        *,
        source: SourceSpec,
        drafts: list[ChunkDraft],
    ) -> list[Chunk]:
        """Persist one :class:`Document` + N :class:`Chunk` rows.

        The document is created lazily here (the worker
        doesn't read :class:`Document` ahead of the parse —
        the parse knows the title, but the document needs a
        persistent primary key, so we create it now and
        attach chunks immediately).
        """
        document = await self._upsert_document(session, source=source)
        chunks: list[Chunk] = []
        for draft in drafts:
            chunk = Chunk(
                document_id=document.document_id,
                product_area=source.product_area,
                section_path=draft.heading,
                heading=draft.heading,
                parent_heading=None,
                chunk_text=draft.text,
                context_summary=draft.text[:120],
                exact_terms=[],
                chunk_order=draft.chunk_order,
                content_checksum=_checksum(draft.text),
                embedding=self._embedder.embed(draft.text),
            )
            session.add(chunk)
            chunks.append(chunk)
        return chunks

    async def _upsert_document(
        self,
        session: AsyncSession,
        *,
        source: SourceSpec,
    ) -> Document:
        """Create or update the :class:`Document` for ``source``.

        Idempotent on ``(source_name, index_version)`` — a
        re-run for the same snapshot finds the existing
        document and stamps ``last_fetched_at`` +
        ``last_indexed_at`` rather than inserting a
        duplicate. The ``content_checksum`` here is a
        placeholder; the real per-chunk checksums live on
        the :class:`Chunk` rows.
        """
        existing = await _find_document_for_source(
            session,
            source_name=source.name,
            index_version=self._index_version,
        )
        if existing is not None:
            existing.last_fetched_at = datetime.now(UTC)
            existing.last_indexed_at = datetime.now(UTC)
            existing.status = DocumentStatus.active
            return existing
        document = Document(
            index_version=self._index_version,
            source_name=source.name,
            product_area=source.product_area,
            source_url=source.location,
            title=source.title,
            content_checksum=_checksum(source.name + source.title),
            last_fetched_at=datetime.now(UTC),
            last_indexed_at=datetime.now(UTC),
            status=DocumentStatus.active,
        )
        session.add(document)
        await session.flush()
        return document

    async def _materialize_terms(
        self,
        session: AsyncSession,
        *,
        source: SourceSpec,
        chunks: list[Chunk],
    ) -> list[ExactTerm]:
        """Extract + persist :class:`ExactTerm` rows for the chunks."""
        terms: list[ExactTerm] = []
        for chunk in chunks:
            # Use the pre-prefix body for term extraction so a
            # term like ``--model`` is not double-counted when
            # the title-prefix re-mentions it. The full text is
            # ``title — heading. body``; the body is what's
            # actually searchable.
            body = (
                chunk.chunk_text.split(". ", 1)[-1]
                if ". " in chunk.chunk_text
                else chunk.chunk_text
            )
            drafts = extract_terms(
                ChunkDraft(
                    chunk_order=chunk.chunk_order,
                    heading=chunk.heading,
                    text=chunk.chunk_text,
                    pre_text=body,
                )
            )
            for draft in drafts:
                term = ExactTerm(
                    term_text=draft.term_text,
                    term_type=draft.term_type,
                    product_area=source.product_area,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                )
                session.add(term)
                terms.append(term)
        return terms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _checksum(text: str) -> str:
    """SHA-256 of ``text`` as a hex string.

    Used for ``Document.content_checksum`` and
    ``Chunk.content_checksum``. The DB column is 128 chars
    so the hex digest fits with room to spare.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Async helpers (kept module-private; tests don't import them directly)
# ---------------------------------------------------------------------------


async def _find_document_for_source(
    session: AsyncSession,
    *,
    source_name: str,
    index_version: str,
) -> Document | None:
    """Return the first :class:`Document` for the given source + version.

    Used by :meth:`IngestionRunner._upsert_document` to
    short-circuit a re-run. Returns ``None`` if no row
    exists.
    """
    stmt = (
        select(Document)
        .where(
            Document.source_name == source_name,
            Document.index_version == index_version,
        )
        .order_by(Document.last_fetched_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


__all__ = [
    "FetchError",
    "IngestionRunner",
    "ParseError",
    "RunResult",
    "ensure_index_version",
]


# ---------------------------------------------------------------------------
# Index-version helper
# ---------------------------------------------------------------------------


async def ensure_index_version(
    session: AsyncSession,
    *,
    index_version: str,
    source_version_hash: str,
) -> IndexVersion:
    """Create the candidate :class:`IndexVersion` if missing.

    The admin route is the only place that promotes a
    candidate to active; the worker just makes sure the
    candidate row exists for the snapshot it just built.
    Idempotent on ``index_version`` — re-running for the
    same version returns the existing row.
    """
    existing = await session.get(IndexVersion, index_version)
    if existing is not None:
        return existing
    row = IndexVersion(
        index_version=index_version,
        status=IndexStatus.candidate,
        source_version_hash=source_version_hash,
        created_at=datetime.now(UTC),
        promoted_at=None,
    )
    session.add(row)
    await session.flush()
    return row
