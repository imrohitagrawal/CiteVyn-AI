"""Tests for :mod:`app.worker.allowlist`."""

from __future__ import annotations

import pytest

from app.worker.allowlist import (
    MVP_SOURCES,
    get_source,
    list_source_names,
)


def test_mvp_sources_is_a_tuple() -> None:
    """The allowlist is a frozen tuple, not a list — the list is compile-time fixed."""
    assert isinstance(MVP_SOURCES, tuple)


def test_mvp_sources_has_four_entries() -> None:
    """Four sources for the MVP: claude_api, claude_code, codex, gemini_api."""
    assert len(MVP_SOURCES) == 4


def test_mvp_source_names_match_demo_catalog() -> None:
    """Source names match the demo catalog in :func:`tests.conftest.seed_catalog`."""
    assert {s.name for s in MVP_SOURCES} == {
        "claude_api",
        "claude_code",
        "codex",
        "gemini_api",
    }


def test_mvp_source_names_are_unique() -> None:
    """Two sources with the same name would collide in :class:`IngestionJob`."""
    names = [s.name for s in MVP_SOURCES]
    assert len(set(names)) == len(names)


def test_get_source_returns_named_source() -> None:
    spec = get_source("claude_api")
    assert spec.name == "claude_api"
    assert spec.product_area == "claude_api"


def test_get_source_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError) as exc_info:
        get_source("does-not-exist")
    assert "does-not-exist" in str(exc_info.value)


def test_list_source_names_returns_tuple() -> None:
    names = list_source_names()
    assert isinstance(names, tuple)
    assert "claude_api" in names


def test_source_spec_is_frozen() -> None:
    """A spec is immutable; mutating a field raises ``FrozenInstanceError``."""
    from dataclasses import FrozenInstanceError

    spec = get_source("codex")
    with pytest.raises(FrozenInstanceError):
        spec.name = "other"  # type: ignore[misc]
