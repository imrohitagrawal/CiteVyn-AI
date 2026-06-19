"""Tests for :mod:`app.worker.embedder` (Slice 8 step 6).

The embedder's contract is ``list[float]`` — the numpy
``.tolist()`` branch used to live on
:class:`PickledEmbedding` and was pushed out to the
producer. These tests pin the contract:

* ``StubEmbedder.embed`` returns a plain list, not a numpy
  array. The numpy gate skips cleanly when numpy isn't
  installed.
* The output is deterministic — same text → same vector.
* The output has the configured dim.
* Two distinct inputs produce vectors that are not equal.
"""

from __future__ import annotations

import pytest

from app.worker.embedder import StubEmbedder, build_embedder


def test_stub_embedder_returns_plain_list() -> None:
    """``embed`` returns a Python ``list``, not numpy."""
    embedder = StubEmbedder(dim=16)
    vector = embedder.embed("hello world")
    assert isinstance(vector, list)
    assert all(isinstance(v, float) for v in vector)


def test_stub_embedder_dim_matches_configured_value() -> None:
    """The output length equals ``embedder.dim``."""
    embedder = StubEmbedder(dim=128)
    assert len(embedder.embed("anything")) == 128


def test_stub_embedder_is_deterministic() -> None:
    """Same text → same vector across calls."""
    embedder = StubEmbedder(dim=64)
    a = embedder.embed("claude opus")
    b = embedder.embed("claude opus")
    assert a == b


def test_stub_embedder_distinct_inputs_diverge() -> None:
    """Different text → different vector."""
    embedder = StubEmbedder(dim=64)
    a = embedder.embed("claude opus")
    b = embedder.embed("gemini flash")
    assert a != b


def test_stub_embedder_values_in_unit_interval() -> None:
    """Values are in [0, 1] (the digest byte / 255 mapping)."""
    embedder = StubEmbedder(dim=64)
    vector = embedder.embed("rate limit env var")
    assert all(0.0 <= v <= 1.0 for v in vector)


def test_stub_embedder_accepts_numpy_array_via_tolist() -> None:
    """If a future embedder uses numpy, ``tolist()`` is the seam.

    The :class:`StubEmbedder` doesn't need numpy. This
    test asserts the contract that *if* a numpy array
    somehow arrived at the producer, the producer's
    responsibility is to convert it — NOT the storage
    layer's. We use numpy to demonstrate the producer
    side; the decorator test in
    :mod:`tests.test_chunk_embedding` already proves the
    storage layer rejects numpy.

    Skipped when numpy is not installed.
    """
    pytest.importorskip("numpy")
    import numpy as np

    embedder = StubEmbedder(dim=32)

    # Pretend a real embedder returns an ndarray. The
    # producer (a future ``VoyageEmbedder``) calls
    # ``.tolist()`` to satisfy the contract.
    raw = np.linspace(-1.0, 1.0, 32, dtype="float32")
    converted: list[float] = list(raw.tolist())  # producer seam

    # The stub doesn't care about the input — it just
    # returns its own vector. The point of this test is
    # that the producer's ``.tolist()`` is well-defined
    # and the contract is honored.
    vector = embedder.embed("anything")
    assert isinstance(vector, list)
    assert len(vector) == 32
    # The converted array satisfies the contract too.
    assert isinstance(converted, list)
    assert all(isinstance(v, float) for v in converted)


def test_build_embedder_returns_stub() -> None:
    """The default factory returns a :class:`StubEmbedder`."""
    embedder = build_embedder()
    assert isinstance(embedder, StubEmbedder)


def test_stub_embedder_dim_is_exposed() -> None:
    """The ``dim`` property is reachable without instantiating a vector."""
    embedder = StubEmbedder(dim=256)
    assert embedder.dim == 256
