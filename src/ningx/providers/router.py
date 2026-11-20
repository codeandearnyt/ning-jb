"""Provider registry and routing.

The routing rules from PRD §6.6-6.7 are enforced here, not in the UI:

* A pinned provider wins; otherwise providers are tried in configured priority.
* A disabled provider, a kind with no adapter in this build, and any remote
  provider while local-only processing is on are all **skipped with a stated
  reason**, so the UI can explain why a configured provider was not used.
* Every switch to a different provider is audited, because a switch means the
  user's data went somewhere else than they last saw.
* Retrying is the adapter's job and is bounded there. This layer only decides
  *which* provider to ask, never how many times.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from ningx.contracts.ai import (
    AIRequest,
    AIResponse,
    ProviderConfig,
    ProviderError,
)
from ningx.contracts.time import utcnow
from ningx.core.ports import AuditEvent, AuditSink
from ningx.providers.base import AIProvider, UnconfiguredProvider
from ningx.providers.catalogue import PROFILES
from ningx.providers.gemini import GeminiProvider

ProviderBuilder = Callable[[ProviderConfig], AIProvider]


class AllProvidersFailed(RuntimeError):
    """Every eligible provider failed. The caller keeps local monitoring running.

    The message is a short, honest summary of what was tried; the full attempts
    are on :attr:`attempts` for the UI and the audit trail.
    """

    def __init__(self, attempts: Sequence[RouteAttempt]) -> None:
        self.attempts = tuple(attempts)
        tried = ", ".join(f"{a.provider_id} ({a.error_class or 'failed'})" for a in attempts)
        super().__init__(f"no provider answered: {tried}" if tried else "no provider is available")


@dataclass(frozen=True)
class RoutingPolicy:
    """User-visible routing settings. Defaults are conservative."""

    pin: str | None = None
    local_only: bool = False
    allow_fallback: bool = True


@dataclass(frozen=True)
class Skip:
    provider_id: str
    reason: str


@dataclass(frozen=True)
class RouteAttempt:
    provider_id: str
    ok: bool
    error_class: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class RoutedResponse:
    response: AIResponse
    attempts: tuple[RouteAttempt, ...]
    used_fallback: bool

    @property
    def provider_id(self) -> str:
        return self.response.provider_id


@dataclass(frozen=True)
class RoutePlan:
    """What the router would do, before doing it. Shown in the UI."""

    primary: str | None
    fallbacks: tuple[str, ...]
    skipped: tuple[Skip, ...]

    @property
    def usable(self) -> bool:
        return self.primary is not None or bool(self.fallbacks)


class ProviderRegistry:
    """Builds an adapter for a configuration. No network call happens here."""

    def __init__(
        self,
        secrets: object,
        *,
        gemini_factory: Callable[[ProviderConfig, object], AIProvider] | None = None,
    ) -> None:
        self._secrets = secrets
        self._gemini_factory = gemini_factory

    def build(self, config: ProviderConfig) -> AIProvider:
        profile = PROFILES[config.kind]
        if not profile.implemented:
            return UnconfiguredProvider(config, profile.note)
        if config.kind == "gemini":
            if self._gemini_factory is not None:
                return self._gemini_factory(config, self._secrets)
            return GeminiProvider(config, self._secrets)
        return UnconfiguredProvider(config, "no adapter is registered for this provider")


@dataclass
class ProviderRouter:
    """Chooses a provider and reports every decision it made."""

    configs: Sequence[ProviderConfig]
    registry: ProviderRegistry
    audit: AuditSink | None = None
    clock: Callable[[], datetime] = utcnow
    _skipped: tuple[Skip, ...] = field(default=(), init=False)

    def plan(self, policy: RoutingPolicy) -> RoutePlan:
        skipped: list[Skip] = []
        usable: list[ProviderConfig] = []

        for config in self.configs:
            reason = _rejection(config, policy)
            if reason is not None:
                skipped.append(Skip(config.provider_id, reason))
                continue
            usable.append(config)

        ordered = sorted(usable, key=lambda item: (item.priority, item.name))
        primary: str | None = None

        if policy.pin:
            if any(config.provider_id == policy.pin for config in ordered):
                primary = policy.pin
            elif not any(skip.provider_id == policy.pin for skip in skipped):
                # The pinned provider is not configured at all. Say so rather
                # than quietly substituting one the user did not choose.
                skipped.append(Skip(policy.pin, "pinned provider is not configured"))
        elif ordered:
            primary = ordered[0].provider_id

        fallbacks: tuple[str, ...] = ()
        if policy.allow_fallback:
            fallbacks = tuple(
                config.provider_id
                for config in ordered
                if config.provider_id != primary and config.fallback_ok
            )
        return RoutePlan(primary=primary, fallbacks=fallbacks, skipped=tuple(skipped))

    def generate(self, request: AIRequest, policy: RoutingPolicy) -> RoutedResponse:
        plan = self.plan(policy)
        order = ([plan.primary] if plan.primary else []) + list(plan.fallbacks)
        if not order:
            raise AllProvidersFailed(())
        by_id = {config.provider_id: config for config in self.configs}

        attempts: list[RouteAttempt] = []
        for index, provider_id in enumerate(order):
            config = by_id[provider_id]
            provider = self.registry.build(config)
            if index > 0:
                self._audit_switch(from_id=order[index - 1], to_id=provider_id, attempts=attempts)
            try:
                response = provider.generate(request)
            except ProviderError as exc:
                attempts.append(
                    RouteAttempt(
                        provider_id=provider_id,
                        ok=False,
                        error_class=exc.error_class.value,
                        detail=exc.user_message(),
                    )
                )
                continue
            attempts.append(RouteAttempt(provider_id=provider_id, ok=True))
            return RoutedResponse(
                response=response,
                attempts=tuple(attempts),
                # A response from a fallback is a fallback even when the pinned
                # provider was never reachable.
                used_fallback=index > 0 or plan.primary is None,
            )

        raise AllProvidersFailed(attempts)

    def _audit_switch(
        self, *, from_id: str, to_id: str, attempts: Sequence[RouteAttempt]
    ) -> None:
        if self.audit is None:
            return
        previous = attempts[-1] if attempts else None
        self.audit.append(
            AuditEvent(
                actor="provider:router",
                event_type="provider.switched",
                subject_id=to_id,
                detail={
                    "from": from_id,
                    "to": to_id,
                    "reason": None if previous is None else previous.error_class,
                    "at": self.clock().isoformat(),
                },
            )
        )


def _rejection(config: ProviderConfig, policy: RoutingPolicy) -> str | None:
    if not config.enabled:
        return "disabled"
    profile = PROFILES[config.kind]
    if not profile.implemented:
        return profile.note
    if policy.local_only and not (config.is_local or profile.is_local):
        return "local-only processing is enabled, so a cloud provider is not used"
    return None


__all__ = [
    "AllProvidersFailed",
    "ProviderRegistry",
    "ProviderRouter",
    "RouteAttempt",
    "RoutePlan",
    "RoutedResponse",
    "RoutingPolicy",
    "Skip",
]
