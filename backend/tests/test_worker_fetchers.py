"""Tests for :mod:`app.worker.fetchers`."""

from __future__ import annotations

import pytest

from app.worker.allowlist import SourceSpec
from app.worker.fetchers import (
    FetchError,
    HttpFetcher,
    LocalFetcher,
    build_fetcher,
)


def _spec(location: str) -> SourceSpec:
    return SourceSpec(
        name="test",
        product_area="test",
        title="Test Source",
        fetcher="local",
        location=location,
    )


def test_local_fetcher_reads_existing_fixture() -> None:
    """The Claude API fixture is read and returned as a str."""
    fetcher = LocalFetcher()
    raw = fetcher.fetch(_spec("tests/fixtures/sources/claude_api.md"))
    assert isinstance(raw, str)
    assert "Claude API Reference" in raw
    assert "Rate limits" in raw


def test_local_fetcher_missing_file_raises_fetch_error() -> None:
    """A missing file is a :class:`FetchError`, not an :class:`OSError`."""
    fetcher = LocalFetcher()
    with pytest.raises(FetchError) as exc_info:
        fetcher.fetch(_spec("tests/fixtures/sources/does-not-exist.md"))
    assert "not found" in str(exc_info.value)


def test_build_fetcher_returns_local_for_local_spec() -> None:
    """``build_fetcher`` picks :class:`LocalFetcher` for ``fetcher='local'``."""
    fetcher = build_fetcher(_spec("tests/fixtures/sources/claude_api.md"))
    assert isinstance(fetcher, LocalFetcher)


def test_build_fetcher_returns_http_for_http_spec() -> None:
    """``build_fetcher`` picks :class:`HttpFetcher` for ``fetcher='http'``."""
    spec = SourceSpec(
        name="remote",
        product_area="remote",
        title="Remote",
        fetcher="http",
        location="https://example.com/docs",
    )
    fetcher = build_fetcher(spec)
    assert isinstance(fetcher, HttpFetcher)


def test_http_fetcher_raises_in_mvp() -> None:
    """The MVP HttpFetcher is a placeholder — calling it raises."""
    spec = SourceSpec(
        name="remote",
        product_area="remote",
        title="Remote",
        fetcher="http",
        location="https://example.com/docs",
    )
    fetcher = HttpFetcher()
    with pytest.raises(FetchError) as exc_info:
        fetcher.fetch(spec)
    assert "not wired" in str(exc_info.value).lower()
