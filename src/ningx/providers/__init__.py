"""Provider adapters.

Only :mod:`ningx.providers.gemini` implements a real adapter in this build. The
catalogue names every other supported provider and marks it unbuilt, so the UI
can say "adapter not built yet" instead of pretending a disabled row is a
working integration.
"""

from __future__ import annotations

from ningx.providers.base import (
    AIProvider,
    UnconfiguredProvider,
    call_with_retries,
    estimate_tokens,
    retry_delays,
)
from ningx.providers.catalogue import (
    PROFILES,
    ProviderProfile,
    implemented_kinds,
    profile_for,
)

__all__ = [
    "PROFILES",
    "AIProvider",
    "ProviderProfile",
    "UnconfiguredProvider",
    "call_with_retries",
    "estimate_tokens",
    "implemented_kinds",
    "profile_for",
    "retry_delays",
]
