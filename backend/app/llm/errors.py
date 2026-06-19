"""Typed LLM errors.

The answer engine catches :class:`LLMUnavailable` and surfaces it as
``internal_error`` (or ``cost_limit_reached``, depending on cause). The
separation lets the orchestrator distinguish a transport problem
(provider down, 5xx, timeout) from a malformed-prompt problem, which
it would not want to retry.
"""

from __future__ import annotations


class LLMUnavailable(RuntimeError):
    """Raised when the LLM provider is unreachable or returns 5xx.

    Carries the original cause so the orchestrator can log it. The
    client never swallows the underlying exception.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause
