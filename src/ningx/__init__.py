"""NingX-Optimizer — AI-assisted Windows performance and maintenance.

Core principle: AI may reason and recommend, but never executes. Every system
modification is expressed as a typed :class:`~ningx.contracts.action.Action` and
must pass the deterministic policy engine before any executor sees it.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
