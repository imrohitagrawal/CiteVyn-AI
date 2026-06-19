"""Source allowlist for the ingestion worker.

The MVP source list lives in code so the worker is hermetic
and reproducible — there is no separate ``sources.yaml`` for
the worker to read at boot. The lock between this list and
the actual production source feed is the ``source_version_hash``
column on :class:`IndexVersion`: when an external operator
publishes a new "official docs snapshot", they update
:meth:`SOURCE_VERSION_HASH` and the next worker run produces a
new ``IndexVersion(index_version=..., source_version_hash=...)``.

Design notes
------------
* ``SourceSpec`` is a frozen dataclass — the allowlist is
  compile-time fixed, not runtime-mutable.
* The four MVP sources match the demo catalog in
  :func:`tests.conftest.seed_catalog` so a freshly-built
  ``candidate`` index contains the same docs the demo runs
  against.
* The single source of truth is :data:`MVP_SOURCES`. Tests
  must reference this list (not redefine it) so a future
  source addition only changes one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    """One allowed ingestion source.

    ``name`` is the short identifier used by the
    :class:`IngestionJob.source_name` column and the admin
    list endpoint. ``product_area`` is the product the doc
    belongs to (used for exact-term lookup scoping).
    ``fetcher`` is the implementation key — ``"local"`` for
    the test fixtures and ``"http"`` for production URLs.
    The CLI switches on it in :mod:`app.worker.cli`.
    """

    name: str
    product_area: str
    title: str
    fetcher: str
    location: str


# ---------------------------------------------------------------------------
# MVP source list
# ---------------------------------------------------------------------------
#
# Keep in lock-step with the demo catalog used by
# :func:`tests.conftest.seed_catalog`. The four sources are
# Claude API, Claude Code, Codex, and Gemini API — the four
# products the MVP demo references. Adding a fifth source is
# a deliberate operation; an SRE adds it here AND seeds the
# test fixture so the demo catalog stays consistent.

MVP_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        name="claude_api",
        product_area="claude_api",
        title="Claude API Reference",
        fetcher="local",
        location="tests/fixtures/sources/claude_api.md",
    ),
    SourceSpec(
        name="claude_code",
        product_area="claude_code",
        title="Claude Code Reference",
        fetcher="local",
        location="tests/fixtures/sources/claude_code.md",
    ),
    SourceSpec(
        name="codex",
        product_area="codex",
        title="Codex CLI Reference",
        fetcher="local",
        location="tests/fixtures/sources/codex.md",
    ),
    SourceSpec(
        name="gemini_api",
        product_area="gemini_api",
        title="Gemini API Reference",
        fetcher="local",
        location="tests/fixtures/sources/gemini_api.md",
    ),
)


def get_source(name: str) -> SourceSpec:
    """Return the source spec for ``name`` or raise :class:`KeyError`.

    The CLI uses this for ``citevyn-worker run --source codex``
    so a typo'd name fails fast with a clear error.
    """
    for spec in MVP_SOURCES:
        if spec.name == name:
            return spec
    raise KeyError(f"unknown source: {name!r}. Known: {[s.name for s in MVP_SOURCES]}")


def list_source_names() -> tuple[str, ...]:
    """Return the ordered list of source names."""
    return tuple(spec.name for spec in MVP_SOURCES)


__all__ = [
    "MVP_SOURCES",
    "SourceSpec",
    "get_source",
    "list_source_names",
]
