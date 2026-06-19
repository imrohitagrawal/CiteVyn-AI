"""Embedding generation for the worker.

The MVP uses a deterministic stub. The interface is shaped
so swapping in a real client (``voyage-3`` per
:attr:`Settings.embedding_model`) is a one-line change at
the call site. The contract is strict: :func:`embed` always
returns a plain ``list[float]`` so the storage layer
(:class:`PickledEmbedding`) does not have to do any
runtime type checking.

Design notes
------------
* Determinism: the stub hashes the input text and maps the
  digest into a fixed-dimension vector. Same input → same
  vector, every run. This is what makes the test suite
  hermetic.
* ``list[float]`` is the contract. Numpy is not a hard
  project dependency; if a future implementation wants to
  use ``numpy`` internally for performance, it converts
  to ``list[float]`` at this boundary so the storage
  layer never has to deal with an ``ndarray``.
* :class:`StubEmbedder` is a singleton-like callable; the
  runner instantiates it once at boot and reuses the
  instance for the whole run.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


class Embedder(Protocol):
    """Compute a fixed-dimension vector for ``text``."""

    @property
    def dim(self) -> int:
        """The vector dimension this embedder produces."""
        ...

    def embed(self, text: str) -> list[float]:
        """Return a ``list[float]`` of length :attr:`dim`."""
        ...


@dataclass(frozen=True)
class StubEmbedder:
    """Deterministic test embedder.

    Same input → same vector (modulo dim). The vector is
    derived from SHA-256 of the input so a one-character
    change in the input changes most of the output
    coordinates — sufficient to distinguish chunks in the
    retriever's tests.
    """

    dim: int = 64

    def embed(self, text: str) -> list[float]:
        """Return a ``list[float]`` of length :attr:`dim`.

        Pure function (no I/O, no numpy). The vector is
        ``[byte/255, byte/255, ...]`` for the first
        ``dim`` bytes of the SHA-256 digest. ``byte / 255``
        keeps the values in ``[0, 1]`` so cosine similarity
        behaves like a proper "term frequency" proxy.
        """
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Stretch the digest by repeating it so a 64-dim
        # vector doesn't truncate to the first 64 bytes of
        # one SHA-256.
        stretched = (digest * ((self.dim // len(digest)) + 1))[: self.dim]
        return [byte / 255.0 for byte in stretched]


def build_embedder() -> Embedder:
    """Return the default embedder.

    The MVP always returns :class:`StubEmbedder` — the
    real ``voyage-3`` client lands in Step 7+. Tests use
    this factory to inject a custom dim if they need to.
    """
    return StubEmbedder()


__all__ = [
    "Embedder",
    "StubEmbedder",
    "build_embedder",
]
