"""The provider interface and the shared retry policy.

Every adapter implements :class:`AIProvider`. The retry rule lives here so no
adapter invents its own: only transient failures are retried, with bounded
exponential backoff, and the attempt count is the configured number of total
attempts rather than an unbounded loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from ningx.contracts.ai import (
    AIRequest,
    AIResponse,
    ConnectionResult,
    ErrorClass,
    ModelInfo,
    ProviderCapabilities,
    ProviderConfig,
    ProviderError,
    UsageEstimate,
    ValidationResult,
)

DEFAULT_BASE_DELAY_S = 0.5
DEFAULT_MAX_DELAY_S = 8.0


class AIProvider(Protocol):
    """PRD §6.5 unified provider interface."""

    @property
    def config(self) -> ProviderConfig: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def validate_config(self) -> ValidationResult: ...

    def test_connection(self) -> ConnectionResult: ...

    def list_models(self) -> list[ModelInfo]: ...

    def generate(self, request: AIRequest) -> AIResponse: ...

    def estimate_usage(self, request: AIRequest) -> UsageEstimate: ...


def retry_delays(
    attempts: int,
    *,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
) -> tuple[float, ...]:
    """The backoff schedule *between* attempts.

    ``attempts`` counts the first try, so ``attempts=1`` yields no delays and
    ``attempts=3`` yields two. Pure, so the schedule is testable without waiting.
    """
    if attempts <= 1:
        return ()
    return tuple(
        min(base_delay_s * (2**index), max_delay_s) for index in range(attempts - 1)
    )


def call_with_retries[T](
    operation: Callable[[], T],
    *,
    attempts: int,
    sleep: Callable[[float], None] = time.sleep,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
) -> T:
    """Run ``operation``, retrying only :class:`ProviderError` failures that are
    transient. Anything else propagates on the first occurrence."""
    delays = retry_delays(attempts, base_delay_s=base_delay_s, max_delay_s=max_delay_s)
    for delay in (*delays, None):
        try:
            return operation()
        except ProviderError as exc:
            if delay is None or not exc.retryable:
                raise
            sleep(delay)
    raise AssertionError("unreachable: the loop either returns or raises")  # pragma: no cover


class UnconfiguredProvider:
    """Stands in for a provider that has no credential or no adapter.

    It answers ``validate_config`` with the real reason and raises
    :class:`ProviderError` for every operation that would need the network. This
    is what the UI binds to before a key is entered, so "not configured" is a
    measured state rather than a disabled button with no explanation.
    """

    def __init__(self, config: ProviderConfig, reason: str) -> None:
        self._config = config
        self._reason = reason

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    @property
    def reason(self) -> str:
        return self._reason

    def validate_config(self) -> ValidationResult:
        return ValidationResult(problems=(self._reason,))

    def test_connection(self) -> ConnectionResult:
        return ConnectionResult(
            ok=False,
            detail=self._reason,
            error_class=ErrorClass.NOT_CONFIGURED,
        )

    def list_models(self) -> list[ModelInfo]:
        raise ProviderError(ErrorClass.NOT_CONFIGURED, self._reason)

    def generate(self, request: AIRequest) -> AIResponse:
        raise ProviderError(ErrorClass.NOT_CONFIGURED, self._reason)

    def estimate_usage(self, request: AIRequest) -> UsageEstimate:
        raise ProviderError(ErrorClass.NOT_CONFIGURED, self._reason)


def estimate_tokens(text: str) -> int:
    """A labelled heuristic: about four characters per token.

    Only ever surfaced through :class:`UsageEstimate`, never as measured usage.
    """
    return max(1, (len(text) + 3) // 4)


__all__ = [
    "DEFAULT_BASE_DELAY_S",
    "DEFAULT_MAX_DELAY_S",
    "AIProvider",
    "UnconfiguredProvider",
    "call_with_retries",
    "estimate_tokens",
    "retry_delays",
]
