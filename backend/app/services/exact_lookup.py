"""Exact-term lookup service.

Backs the public :http:post:`/v1/search/exact` route. The intent is
"did the user paste a known flag, command, config key, or model
name?" — if so, return the canonical chunk(s) that contain it,
without paying for a vector roundtrip. The service is a thin
SQLAlchemy query helper; the policy (rate limiting, audit, response
shape) lives in the route.

Design choices
--------------

- **Product area is mandatory** — the same flag name in
  ``claude-code`` vs ``anthropic-sdk-python`` is a different answer.
  We refuse the request rather than silently fall back to a
  global search, because global would mix products.
- **Index-version filtering is optional but recommended** — the
  caller can pin to ``active`` (default) or pass a specific
  ``index_version`` for replay / debugging.
- **Result cap is server-controlled** — the service clamps to
  :data:`MAX_RESULTS` regardless of what the caller asks for,
  to bound the response size.
- **No fuzzy match** — exact-lookup is binary: term is in
  ``exact_terms`` or it is not. Spelling variants belong in the
  hybrid-search path (slice 8 step 4+) or a future
  ``/v1/search/suggest`` route.

The module is dependency-injectable: :func:`exact_lookup` takes an
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and returns a list
of plain dataclasses that the route layer can serialise.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document
from app.models.enums import IndexStatus, TermType
from app.models.exact_terms import ExactTerm
from app.models.index_versions import IndexVersion

#: Hard cap on the number of hits returned in one response.
#: Bigger requests are clamped to this value; the route layer
#: also enforces it before the service is called.
MAX_RESULTS = 25


@dataclass(frozen=True)
class ExactLookupHit:
    """One match returned by :func:`exact_lookup`.

    Plain dataclass (not a Pydantic model) because the service
    is a transport-agnostic helper — the route layer wraps it
    in a response model.
    """

    term_id: str
    term_text: str
    term_type: TermType
    product_area: str
    document_id: str
    chunk_id: str
    index_version: str
    score: float  # always 1.0 for exact lookups; kept for shape parity with hybrid search


async def exact_lookup(
    session: AsyncSession,
    *,
    term: str,
    product_area: str,
    term_type: TermType | None = None,
    index_version: str = "active",
    limit: int = MAX_RESULTS,
) -> list[ExactLookupHit]:
    """Return exact-term matches for ``term`` in ``product_area``.

    Parameters
    ----------
    session
        Open async session. The function does not commit — the
        caller controls the transaction boundary.
    term
        The exact string the user pasted. The comparison is
        case-sensitive (canonical flag / config names are
        case-sensitive by convention).
    product_area
        Filter on the ``exact_terms.product_area`` column.
        Required because the same term name can mean different
        things in different products.
    term_type
        Optional filter on the term type (e.g. only ``flag``
        hits). When ``None`` all term types are returned.
    index_version
        ``"active"`` (default) restricts to the currently
        promoted index; any other string is treated as a
        specific :class:`IndexVersion` key.
    limit
        Maximum number of hits to return. Clamped to
        :data:`MAX_RESULTS`.

    Returns
    -------
    list[ExactLookupHit]
        Empty list when no match exists. Never ``None``.
    """
    if not term:
        # Defensive guard — the route layer already validates,
        # but a refactor could forget. Return empty rather than
        # raise so the caller doesn't have to wrap.
        return []
    if not product_area:
        # Same: product area is mandatory; empty means "global"
        # which we don't support.
        return []

    capped_limit = max(1, min(limit, MAX_RESULTS))

    # Build the base query. We join to documents so we can filter
    # on the index version attached to the source document; the
    # join is on the FK the model already declares.
    stmt = (
        select(ExactTerm, ExactTerm.document_id, ExactTerm.chunk_id)
        .where(ExactTerm.term_text == term)
        .where(ExactTerm.product_area == product_area)
    )

    if term_type is not None:
        stmt = stmt.where(ExactTerm.term_type == term_type)

    # Filter on the active index, unless the caller pinned a
    # specific one (e.g. for replay). The "active" string is
    # the sentinel — a real index_version is just a string PK.
    if index_version == "active":
        # Join to the document's index_version column and filter on
        # its status. The relationship is `lazy="raise"` so we
        # must use ``joinedload`` or an explicit join; explicit
        # join keeps the SQL predictable.
        stmt = stmt.join(Document, ExactTerm.document_id == Document.document_id).where(
            Document.index_version.in_(
                select(IndexVersion.index_version).where(IndexVersion.status == IndexStatus.active)
            )
        )
    else:
        stmt = stmt.join(Document, ExactTerm.document_id == Document.document_id).where(
            Document.index_version == index_version
        )

    stmt = stmt.limit(capped_limit)

    rows = (await session.execute(stmt)).all()

    hits: list[ExactLookupHit] = []
    for row in rows:
        # ``row`` is a Row; first element is the ExactTerm ORM
        # instance, the rest are the selected columns.
        term_row: ExactTerm = row[0]
        hits.append(
            ExactLookupHit(
                term_id=str(term_row.term_id),
                term_text=term_row.term_text,
                term_type=term_row.term_type,
                product_area=term_row.product_area,
                document_id=str(row[1]),
                chunk_id=str(row[2]),
                index_version=index_version,
                score=1.0,
            )
        )
    return hits


__all__ = ["ExactLookupHit", "exact_lookup", "MAX_RESULTS"]
