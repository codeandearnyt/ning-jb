"""Routing: which provider is asked, which is skipped, and why.

The router is the only place that decides a provider switch, so every rule the
PRD states about fallback and local-only processing is checked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from ningx.contracts.ai import (
    AIMessage,
    AIRequest,
    AIResponse,
    ErrorClass,
    ProviderConfig,
    ProviderError,
    TokenUsage,
    UsageSource,
)
from ningx.core.ports import AuditEvent
from ningx.providers.router import (
    AllProvidersFailed,
    ProviderRegistry,
    ProviderRouter,
    RoutingPolicy,
)

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def recent(self, limit: int = 100) -> list[AuditEvent]:
        return self.events[-limit:]


@dataclass
class ScriptedProvider:
    config: ProviderConfig
    text: str = "answer"
    error: ProviderError | None = None
    calls: list[AIRequest] = field(default_factory=list)

    def generate(self, request: AIRequest) -> AIResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return AIResponse(
            provider_id=self.config.provider_id,
            kind="gemini",
            model=self.config.model_id or "model",
            text=self.text,
            latency_ms=12.0,
            usage=TokenUsage(input_tokens=10, output_tokens=2, source=UsageSource.PROVIDER),
        )


def config(provider_id: str, **overrides: object) -> ProviderConfig:
    base: dict[str, object] = {
        "provider_id": provider_id,
        "name": provider_id.title(),
        "kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "secret_ref": f"provider/{provider_id}",
    }
    base.update(overrides)
    return ProviderConfig.model_validate(base)


def request() -> AIRequest:
    return AIRequest(messages=(AIMessage(role="user", content="hello"),))


class Harness:
    """A router wired to scripted providers keyed by provider id."""

    def __init__(self, configs: list[ProviderConfig], script: dict[str, ScriptedProvider]):
        self.script = script
        self.audit = RecordingAudit()
        self.registry = ProviderRegistry(
            object(), gemini_factory=lambda config, secrets: script[config.provider_id]
        )
        self.router = ProviderRouter(
            configs, self.registry, audit=self.audit, clock=lambda: START
        )


def harness(*specs: tuple[ProviderConfig, ProviderError | None]) -> Harness:
    configs: list[ProviderConfig] = []
    script: dict[str, ScriptedProvider] = {}
    for spec, error in specs:
        configs.append(spec)
        script[spec.provider_id] = ScriptedProvider(spec, error=error)
    return Harness(configs, script)


# ------------------------------------------------------------------------ plan


def test_the_lowest_priority_number_is_primary() -> None:
    h = harness((config("slow", priority=90), None), (config("fast", priority=10), None))
    plan = h.router.plan(RoutingPolicy())
    assert plan.primary == "fast"
    assert plan.usable


def test_a_disabled_provider_is_skipped_with_a_stated_reason() -> None:
    h = harness((config("off", enabled=False), None), (config("on", priority=50), None))
    plan = h.router.plan(RoutingPolicy())
    assert plan.primary == "on"
    assert plan.skipped[0].provider_id == "off"
    assert plan.skipped[0].reason == "disabled"


def test_a_provider_without_an_adapter_is_skipped_with_its_catalogue_note() -> None:
    h = harness((config("remote", kind="openai"), None), (config("local", priority=50), None))
    plan = h.router.plan(RoutingPolicy())
    assert plan.primary == "local"
    assert "not built yet" in plan.skipped[0].reason


def test_local_only_processing_skips_every_cloud_provider() -> None:
    h = harness((config("cloud"), None))
    plan = h.router.plan(RoutingPolicy(local_only=True))
    assert plan.primary is None
    assert "local-only" in plan.skipped[0].reason


def test_local_only_processing_still_allows_a_local_provider() -> None:
    h = harness(
        (config("cloud", priority=1), None),
        (config("box", kind="ollama", priority=50), None),
    )
    # ollama has no adapter in this build, so it is skipped for that reason, not
    # for being local.
    plan = h.router.plan(RoutingPolicy(local_only=True))
    assert plan.primary is None
    reasons = {skip.provider_id: skip.reason for skip in plan.skipped}
    assert "local-only" in reasons["cloud"]
    assert "local-only" not in reasons["box"]


def test_a_pinned_provider_wins_over_priority() -> None:
    h = harness((config("first", priority=1), None), (config("chosen", priority=90), None))
    assert h.router.plan(RoutingPolicy(pin="chosen")).primary == "chosen"


def test_pinning_an_unavailable_provider_is_reported_and_not_substituted() -> None:
    h = harness((config("first", priority=1), None))
    plan = h.router.plan(RoutingPolicy(pin="ghost"))

    # The user's explicit choice is not quietly replaced by another provider.
    assert plan.primary is None
    assert any(skip.provider_id == "ghost" and "pinned" in skip.reason for skip in plan.skipped)


def test_a_disabled_pin_names_the_real_reason() -> None:
    h = harness((config("chosen", enabled=False), None), (config("other", priority=9), None))
    plan = h.router.plan(RoutingPolicy(pin="chosen"))

    assert plan.primary is None
    assert any(skip.provider_id == "chosen" and skip.reason == "disabled" for skip in plan.skipped)


def test_a_pinned_provider_that_fails_falls_back_and_is_audited() -> None:
    h = harness(
        (config("chosen", priority=1), ProviderError(ErrorClass.SERVER, "503")),
        (config("spare", priority=2, fallback_ok=True), None),
    )
    routed = h.router.generate(request(), RoutingPolicy(pin="chosen"))

    assert routed.provider_id == "spare"
    assert routed.used_fallback is True
    assert h.audit.events[0].detail["from"] == "chosen"


def test_only_fallback_eligible_providers_are_listed_as_fallbacks() -> None:
    h = harness(
        (config("primary", priority=1), None),
        (config("spare", priority=2, fallback_ok=True), None),
        (config("not-spare", priority=3, fallback_ok=False), None),
    )
    plan = h.router.plan(RoutingPolicy())
    assert plan.fallbacks == ("spare",)


def test_fallback_can_be_turned_off_entirely() -> None:
    h = harness(
        (config("primary", priority=1), None),
        (config("spare", priority=2, fallback_ok=True), None),
    )
    assert h.router.plan(RoutingPolicy(allow_fallback=False)).fallbacks == ()


# -------------------------------------------------------------------- generate


def test_the_primary_provider_is_used_without_a_switch() -> None:
    h = harness((config("only"), None))
    routed = h.router.generate(request(), RoutingPolicy())

    assert routed.provider_id == "only"
    assert routed.used_fallback is False
    assert h.audit.events == []


def test_a_failing_primary_falls_back_and_the_switch_is_audited() -> None:
    h = harness(
        (config("primary", priority=1), ProviderError(ErrorClass.SERVER, "503")),
        (config("spare", priority=2, fallback_ok=True), None),
    )
    routed = h.router.generate(request(), RoutingPolicy())

    assert routed.provider_id == "spare"
    assert routed.used_fallback is True
    assert [attempt.provider_id for attempt in routed.attempts] == ["primary", "spare"]
    assert routed.attempts[0].error_class == "server"

    assert len(h.audit.events) == 1
    event = h.audit.events[0]
    assert event.event_type == "provider.switched"
    assert event.detail["from"] == "primary"
    assert event.detail["to"] == "spare"
    assert event.detail["reason"] == "server"


def test_a_non_eligible_provider_is_never_used_as_a_fallback() -> None:
    h = harness(
        (config("primary", priority=1), ProviderError(ErrorClass.AUTH, "401")),
        (config("spare", priority=2, fallback_ok=False), None),
    )
    with pytest.raises(AllProvidersFailed) as caught:
        h.router.generate(request(), RoutingPolicy())

    assert [attempt.provider_id for attempt in caught.value.attempts] == ["primary"]
    assert h.script["spare"].calls == []


def test_every_failure_is_reported_with_its_class() -> None:
    h = harness(
        (config("a", priority=1), ProviderError(ErrorClass.AUTH, "401")),
        (config("b", priority=2, fallback_ok=True), ProviderError(ErrorClass.TIMEOUT, "slow")),
    )
    with pytest.raises(AllProvidersFailed) as caught:
        h.router.generate(request(), RoutingPolicy())

    assert [(a.provider_id, a.error_class) for a in caught.value.attempts] == [
        ("a", "auth"),
        ("b", "timeout"),
    ]
    assert "no provider answered" in str(caught.value)


def test_no_usable_provider_fails_without_inventing_one() -> None:
    h = harness((config("cloud"), None))
    with pytest.raises(AllProvidersFailed) as caught:
        h.router.generate(request(), RoutingPolicy(local_only=True))

    assert caught.value.attempts == ()
    assert h.audit.events == []


def test_the_audit_event_never_carries_a_credential() -> None:
    h = harness(
        (config("primary", priority=1), ProviderError(ErrorClass.AUTH, "bad key")),
        (config("spare", priority=2, fallback_ok=True), None),
    )
    h.router.generate(request(), RoutingPolicy())

    rendered = repr(h.audit.events[0].detail)
    assert "key" not in rendered.lower().replace("reason", "")


def test_the_registry_returns_a_stand_in_for_a_kind_with_no_adapter() -> None:
    registry = ProviderRegistry(object())
    built = registry.build(config("remote", kind="openai"))

    assert "not built yet" in built.validate_config().problems[0]
    assert built.capabilities.json_mode is False
