"""Provider screen view model: states, rows and honest number formatting.

The rules this module encodes:

* A provider with no adapter in this build says so, and is never shown as ready.
* A provider with no stored credential is "no credential", not "offline".
* A missing statistic is an em dash with a reason, never a zero.
* A connection test that never ran is "never tested", not "unknown error".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ningx.contracts.ai import ConnectionResult, ProviderConfig, ProviderKind
from ningx.providers.catalogue import PROFILES, ProviderProfile
from ningx.storage.repositories.providers import MIN_SAMPLES_FOR_P95, UsageSummary

SECRET_REF_PREFIX = "provider/"  # noqa: S105 - a vault reference, not a credential
DASH = "\u2014"


class ProviderState(StrEnum):
    UNBUILT = "unbuilt"
    DISABLED = "disabled"
    NO_CREDENTIAL = "no_credential"
    NO_MODEL = "no_model"
    READY = "ready"


_STATE_LABEL: dict[ProviderState, str] = {
    ProviderState.UNBUILT: "NOT BUILT",
    ProviderState.DISABLED: "DISABLED",
    ProviderState.NO_CREDENTIAL: "NO CREDENTIAL",
    ProviderState.NO_MODEL: "NO MODEL",
    ProviderState.READY: "READY",
}


def secret_ref_for(provider_id: str) -> str:
    return f"{SECRET_REF_PREFIX}{provider_id}"


def profile_of(kind: ProviderKind) -> ProviderProfile:
    return PROFILES[kind]


def new_config(provider_id: str, kind: ProviderKind, *, name: str | None = None) -> ProviderConfig:
    """A draft configuration with nothing invented.

    No model is pre-filled: the model list belongs to the credential, so the
    user fetches it rather than being handed a name that may not exist.
    """
    profile = PROFILES[kind]
    return ProviderConfig(
        provider_id=provider_id,
        name=name or profile.label,
        kind=kind,
        is_local=profile.is_local,
        auth_scheme=profile.auth_scheme,
        base_url=profile.default_base_url,
        secret_ref=secret_ref_for(provider_id) if profile.needs_secret else None,
        enabled=False,
    )


def provider_state(
    config: ProviderConfig, *, secret_present: bool
) -> tuple[ProviderState, str]:
    profile = PROFILES[config.kind]
    if not profile.implemented:
        return ProviderState.UNBUILT, profile.note
    if not config.enabled:
        return ProviderState.DISABLED, "Disabled: routing will not select it."
    if profile.needs_secret and not secret_present:
        return (
            ProviderState.NO_CREDENTIAL,
            "No credential is stored in Windows Credential Manager.",
        )
    if not config.model_id:
        return ProviderState.NO_MODEL, "No model is selected. Fetch the list and choose one."
    return ProviderState.READY, "Configured. Run a connection test to confirm it answers."


@dataclass(frozen=True)
class ProviderRow:
    provider_id: str
    name: str
    kind_label: str
    model: str
    state: ProviderState
    state_label: str
    detail: str
    implemented: bool

    @property
    def needs_attention(self) -> bool:
        return self.state is not ProviderState.READY


def build_rows(
    configs: Sequence[ProviderConfig],
    *,
    secret_present: Callable[[str], bool],
) -> tuple[ProviderRow, ...]:
    rows: list[ProviderRow] = []
    for config in configs:
        profile = PROFILES[config.kind]
        has_secret = _safe_secret_check(secret_present, config.secret_ref)
        state, detail = provider_state(config, secret_present=has_secret)
        rows.append(
            ProviderRow(
                provider_id=config.provider_id,
                name=config.name,
                kind_label=profile.label,
                model=config.model_id or DASH,
                state=state,
                state_label=_STATE_LABEL[state],
                detail=detail,
                implemented=profile.implemented,
            )
        )
    return tuple(rows)


def _safe_secret_check(check: Callable[[str], bool], reference: str | None) -> bool:
    if not reference:
        return False
    try:
        return check(reference)
    except Exception:
        # A credential store that cannot be read is not evidence that a
        # credential exists.
        return False


@dataclass(frozen=True)
class UsageView:
    requests: int
    success: str
    median: str
    p95: str
    p95_note: str
    tokens: str
    coverage: str
    last_error: str

    @property
    def empty(self) -> bool:
        return self.requests == 0


def build_usage_view(summary: UsageSummary) -> UsageView:
    if summary.requests == 0:
        return UsageView(
            requests=0,
            success=DASH,
            median=DASH,
            p95=DASH,
            p95_note="No requests recorded yet, so no latency is available.",
            tokens=DASH,
            coverage="No request has been recorded for this provider.",
            last_error=DASH,
        )

    rate = summary.success_rate
    success = DASH if rate is None else f"{rate:.0%} ({summary.successes}/{summary.requests})"
    median = DASH if summary.median_latency_ms is None else f"{summary.median_latency_ms:.0f} ms"

    if summary.p95_latency_ms is None:
        p95 = DASH
        p95_note = (
            f"Needs {MIN_SAMPLES_FOR_P95} latency samples for a p95 "
            f"(have {summary.latency_samples})."
        )
    else:
        p95 = f"{summary.p95_latency_ms:.0f} ms"
        p95_note = f"From {summary.latency_samples} samples."

    if summary.with_usage == 0:
        tokens = f"{DASH} (no request reported token usage)"
    else:
        tokens = f"{summary.input_tokens:,} in \u00b7 {summary.output_tokens:,} out"

    coverage = (
        f"{summary.with_usage} of {summary.requests} requests reported token usage."
    )
    if summary.without_usage:
        coverage += " The rest are not counted as zero."

    return UsageView(
        requests=summary.requests,
        success=success,
        median=median,
        p95=p95,
        p95_note=p95_note,
        tokens=tokens,
        coverage=coverage,
        last_error=summary.last_error_class or "none",
    )


def describe_test(result: ConnectionResult) -> str:
    """One line for the UI. The adapter already wrote a specific detail."""
    if result.ok:
        latency = f"{result.latency_ms:.0f} ms" if result.latency_ms is not None else DASH
        seen = (
            f"{result.models_seen} models"
            if result.models_seen is not None
            else "models unknown"
        )
        return f"Connected in {latency} \u00b7 {seen}. {result.detail}".strip()
    error = result.error_class.value if result.error_class else "unknown"
    return f"Failed ({error}): {result.detail}"


def describe_last_test(config: ProviderConfig) -> str:
    if config.last_test_at is None:
        return "Never tested."
    when = _format_time(config.last_test_at)
    status = config.last_test_status or "unknown"
    return f"Last test {when}: {status}."


def routing_warning(
    *,
    local_only: bool,
    configs: Sequence[ProviderConfig],
    secret_present: Callable[[str], bool],
) -> str | None:
    """A warning when a routing setting makes every provider unusable."""
    if not local_only:
        return None
    usable = [
        config
        for config in configs
        if PROFILES[config.kind].implemented
        and config.enabled
        and provider_state(
            config,
            secret_present=_safe_secret_check(secret_present, config.secret_ref),
        )[0]
        is ProviderState.READY
        and (config.is_local or PROFILES[config.kind].is_local)
    ]
    if usable:
        return None
    return (
        "Local-only processing is on, but no enabled local provider is ready. "
        "Requests will be refused rather than sent to a cloud provider."
    )


def _format_time(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


__all__ = [
    "DASH",
    "SECRET_REF_PREFIX",
    "ProviderRow",
    "ProviderState",
    "UsageView",
    "build_rows",
    "build_usage_view",
    "describe_last_test",
    "describe_test",
    "new_config",
    "profile_of",
    "provider_state",
    "routing_warning",
    "secret_ref_for",
]
