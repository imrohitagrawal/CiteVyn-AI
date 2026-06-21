"""Source fetchers for the ingestion worker.

A fetcher's job is one thing: take a :class:`SourceSpec` and
return the raw bytes/text of the source document. Parsing is a
separate concern (see :mod:`app.worker.parser`).

Design notes
------------
* :class:`Fetcher` is a :class:`Protocol`, not an ABC — the
  runner is duck-typed and tests can build lightweight
  substitutes without inheriting.
* The MVP fetcher is :class:`LocalFetcher` (reads markdown
  fixtures from disk). The HTTP fetcher is sketched but not
  wired — production rollout is a Step 7+ concern, not the
  MVP. The test suite uses :class:`LocalFetcher` exclusively.
* Fetchers are intentionally sync (no ``httpx`` async here).
  The worker CLI drives one document at a time and the
  blocking I/O is bounded; if the worker grows to many
  parallel jobs, swap to :class:`httpx.AsyncClient` here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.worker.allowlist import SourceSpec


class FetchError(Exception):
    """Raised when a fetcher cannot read its source.

    The runner catches this and writes the error type to the
    :class:`IngestionJob.error_type` column. The fetch error
    type is always ``"FetchError"`` — a future network-error
    taxonomy would split this into ``TimeoutError``,
    ``HttpStatusError``, etc.
    """


class Fetcher(Protocol):
    """Read the raw bytes/text of ``source``."""

    def fetch(self, source: SourceSpec) -> str:
        """Return the raw document text for ``source``."""
        ...


class LocalFetcher:
    """Read a fixture file from disk.

    The MVP worker uses this. The path is taken from
    :attr:`SourceSpec.location`; the file is read as UTF-8
    with a strict error handler so an encoding error surfaces
    here rather than as a parse error later.
    """

    def __init__(self, *, root: Path | None = None) -> None:
        """Create a fetcher rooted at ``root``.

        ``root`` is the project root for the relative paths in
        :class:`SourceSpec.location`. The default is the
        backend directory; tests can pass a temp directory
        after building a fixture tree under it.
        """
        self._root = root if root is not None else _default_root()

    def fetch(self, source: SourceSpec) -> str:
        path = self._root / source.location
        if not path.is_file():
            raise FetchError(f"local fixture not found: {path} (source={source.name!r})")
        try:
            return path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise FetchError(f"local fixture is not valid utf-8: {path} ({exc})") from exc


class HttpFetcher:
    """Fetch a remote document over HTTPS.

    The MVP doesn't wire this; the class is the integration
    point for Step 7+ (when we have a stable docs endpoint to
    pull from). The :class:`SourceSpec.fetcher` field
    switches between ``"local"`` and ``"http"`` and the
    :func:`build_fetcher` factory picks accordingly.
    """

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds

    def fetch(self, source: SourceSpec) -> str:
        raise FetchError(
            "HttpFetcher is not wired in the MVP. "
            f"Source {source.name!r} declared fetcher={source.fetcher!r}."
        )


def build_fetcher(source: SourceSpec, *, root: Path | None = None) -> Fetcher:
    """Pick the right fetcher for ``source``.

    The MVP always returns :class:`LocalFetcher` — the
    ``fetcher`` field is here so a future migration is a
    one-line change in this factory.
    """
    if source.fetcher == "http":
        return HttpFetcher()
    return LocalFetcher(root=root)


def _default_root() -> Path:
    """Return the backend directory (the parent of ``app/``)."""
    return Path(__file__).resolve().parent.parent.parent


__all__ = [
    "Fetcher",
    "FetchError",
    "HttpFetcher",
    "LocalFetcher",
    "build_fetcher",
]
