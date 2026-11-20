"""Provider screen view model: every state names itself, no number is invented."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

import ningx.ui.viewmodels.providers as view_model
from ningx.contracts.ai import ConnectionResult, ErrorClass, ProviderConfig
from ningx.storage.repositories.providers import MIN_SAMPLES_FOR_P95, UsageSummary
from ningx.ui.viewmodels.providers import (
    DASH,
    ProviderState,
    build_rows,
    build_usage_view,
    describe_last_test,
    describe_test,
    new_config,
    provider_state,
    routing_warning,
    secret_ref_for,
)

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def config(**overrides: object) -> ProviderConfig:
    base: dict[str, object] = {
        "provider_id": "gemini",
        "name": "Gemini",
        "kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "secret_ref": secret_ref_for("gemini"),
        "enabled": True,
    }
    base.update(overrides)
    return ProviderConfig.model_validate(base)


def summary(
    *,
    requests: int = 4,
    successes: int = 3,
    errors: int = 1,
    with_usage: int = 3,
    without_usage: int = 1,
    input_tokens: int = 1200,
    output_tokens: int = 340,
    latency_samples: int = 4,
    median_latency_ms: float | None = 210.0,
    p95_latency_ms: float | None = None,
    last_error_class: str | None = "rate_limit",
) -> UsageSummary:
    return UsageSummary(
        provider_id="gemini",
        requests=requests,
        successes=successes,
        errors=errors,
        with_usage=with_usage,
        without_usage=without_usage,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_samples=latency_samples,
        median_latency_ms=median_latency_ms,
        p95_latency_ms=p95_latency_ms,
        last_error_class=last_error_class,
    )


# --------------------------------------------------------------------- drafts


def test_a_new_provider_starts_disabled_and_without_an_invented_model() -> None:
    draft = new_config("gemini", "gemini")

    assert draft.enabled is False
    assert draft.model_id is None
    assert draft.secret_ref == "provider/gemini"  # noqa: S105
    assert draft.auth_scheme == "api_key"


def test_a_local_provider_needs_no_credential_reference() -> None:
    assert new_config("ollama", "ollama").secret_ref is None


# ---------------------------------------------------------------------- state


def test_an_unbuilt_kind_says_not_built_before_anything_else() -> None:
    state, detail = provider_state(config(kind="openai"), secret_present=True)
    assert state is ProviderState.UNBUILT
    assert "not built yet" in detail


def test_a_disabled_provider_is_disabled_even_with_a_credential() -> None:
    state, detail = provider_state(config(enabled=False), secret_present=True)
    assert state is ProviderState.DISABLED
    assert "routing will not select it" in detail


def test_a_provider_without_a_stored_credential_says_so() -> None:
    state, detail = provider_state(config(), secret_present=False)
    assert state is ProviderState.NO_CREDENTIAL
    assert "Windows Credential Manager" in detail


def test_a_provider_without_a_model_is_not_ready() -> None:
    state, detail = provider_state(config(model_id=None), secret_present=True)
    assert state is ProviderState.NO_MODEL
    assert "Fetch the list" in detail


def test_a_complete_provider_is_ready_but_still_untested() -> None:
    state, detail = provider_state(config(), secret_present=True)
    assert state is ProviderState.READY
    assert "Run a connection test" in detail


def test_a_provider_that_needs_no_secret_does_not_ask_for_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ollama has no adapter in this build, so pretend it does: the point of this
    # test is the credential rule, not the adapter inventory.
    profiles = dict(view_model.PROFILES)
    profiles["ollama"] = dataclasses.replace(profiles["ollama"], implemented=True)
    monkeypatch.setattr(view_model, "PROFILES", profiles)

    draft = view_model.new_config("box", "ollama", name="Local Ollama").model_copy(
        update={"model_id": "llama3.2", "enabled": True}
    )
    state, _ = view_model.provider_state(draft, secret_present=False)
    assert state is view_model.ProviderState.READY


def test_a_local_kind_without_an_adapter_is_reported_as_unbuilt_not_uncredentialed() -> None:
    state, detail = provider_state(
        new_config("box", "ollama").model_copy(
            update={"enabled": True, "model_id": "llama3.2"}
        ),
        secret_present=False,
    )
    assert state is ProviderState.UNBUILT
    assert "not built yet" in detail


# ----------------------------------------------------------------------- rows


def test_rows_report_the_kind_label_and_never_a_blank_model() -> None:
    rows = build_rows(
        [config(), config(provider_id="local", name="Local", kind="ollama", model_id=None)],
        secret_present=lambda reference: True,
    )

    assert rows[0].kind_label == "Google Gemini"
    assert rows[0].model == "gemini-2.5-flash"
    assert rows[1].model == DASH
    assert rows[1].implemented is False
    assert rows[1].needs_attention


def test_a_credential_store_failure_reads_as_no_credential_not_as_present() -> None:
    def broken(_reference: str) -> bool:
        raise RuntimeError("vault unavailable")

    rows = build_rows([config()], secret_present=broken)
    assert rows[0].state is ProviderState.NO_CREDENTIAL


# ---------------------------------------------------------------------- usage


def test_an_unused_provider_shows_dashes_not_zeroes() -> None:
    view = build_usage_view(UsageSummary(provider_id="gemini"))

    assert view.empty
    assert view.success == DASH
    assert view.median == DASH
    assert view.p95 == DASH
    assert view.tokens == DASH
    assert "No requests recorded" in view.p95_note


def test_a_p95_is_withheld_with_a_count_of_what_is_missing() -> None:
    view = build_usage_view(summary(latency_samples=4))

    assert view.p95 == DASH
    assert str(MIN_SAMPLES_FOR_P95) in view.p95_note
    assert "have 4" in view.p95_note


def test_a_p95_is_shown_once_it_is_meaningful() -> None:
    view = build_usage_view(summary(p95_latency_ms=880.0, latency_samples=40))
    assert view.p95 == "880 ms"
    assert "40 samples" in view.p95_note


def test_success_is_reported_as_a_rate_with_its_counts() -> None:
    assert build_usage_view(summary()).success == "75% (3/4)"


def test_usage_coverage_names_the_requests_that_reported_nothing() -> None:
    view = build_usage_view(summary())
    assert view.coverage == (
        "3 of 4 requests reported token usage. The rest are not counted as zero."
    )


def test_no_reported_usage_is_not_shown_as_zero_tokens() -> None:
    view = build_usage_view(
        summary(with_usage=0, without_usage=4, input_tokens=0, output_tokens=0)
    )
    assert view.tokens == f"{DASH} (no request reported token usage)"


def test_tokens_are_grouped_and_separated() -> None:
    assert build_usage_view(summary()).tokens == "1,200 in \u00b7 340 out"


def test_the_last_error_is_named_or_none() -> None:
    assert build_usage_view(summary()).last_error == "rate_limit"
    assert build_usage_view(summary(last_error_class=None)).last_error == "none"


# ------------------------------------------------------------- test reporting


def test_a_successful_test_reports_latency_and_model_count() -> None:
    text = describe_test(
        ConnectionResult(ok=True, detail="model is visible", latency_ms=250.0, models_seen=12)
    )
    assert "250 ms" in text
    assert "12 models" in text
    assert "model is visible" in text


def test_a_failed_test_names_its_class_and_reason() -> None:
    text = describe_test(
        ConnectionResult(
            ok=False,
            detail="check the stored credential",
            error_class=ErrorClass.AUTH,
        )
    )
    assert text.startswith("Failed (auth)")
    assert "check the stored credential" in text


def test_a_never_tested_provider_says_never_tested() -> None:
    assert describe_last_test(config()) == "Never tested."


def test_a_previous_test_is_dated_and_named() -> None:
    text = describe_last_test(config(last_test_at=START, last_test_status="ok"))
    assert text.startswith("Last test ")
    assert text.endswith(": ok.")


# -------------------------------------------------------------------- routing


def test_local_only_with_no_ready_local_provider_warns_instead_of_going_quiet() -> None:
    warning = routing_warning(
        local_only=True, configs=[config()], secret_present=lambda reference: True
    )
    assert warning is not None
    assert "refused" in warning


def test_local_only_warns_when_the_only_local_kind_has_no_adapter() -> None:
    local = new_config("box", "ollama").model_copy(
        update={"enabled": True, "model_id": "llama3.2"}
    )
    warning = routing_warning(
        local_only=True, configs=[local], secret_present=lambda reference: False
    )
    assert warning is not None
    assert "refused" in warning


def test_local_only_is_fine_when_a_local_provider_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles = dict(view_model.PROFILES)
    profiles["ollama"] = dataclasses.replace(profiles["ollama"], implemented=True)
    monkeypatch.setattr(view_model, "PROFILES", profiles)

    local = view_model.new_config("box", "ollama").model_copy(
        update={"enabled": True, "model_id": "llama3.2"}
    )
    assert (
        view_model.routing_warning(
            local_only=True, configs=[local], secret_present=lambda reference: False
        )
        is None
    )


def test_routing_never_warns_when_cloud_is_allowed() -> None:
    assert (
        routing_warning(local_only=False, configs=[], secret_present=lambda reference: False)
        is None
    )
