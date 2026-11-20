"""Provider layer: retry policy, error mapping, Gemini adapter, honest states.

No test here reaches the network. The SDK client is injected, so a test that
accidentally tries to call Google fails loudly instead of quietly costing the
user a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from google.genai import errors as genai_errors

from ningx.contracts.ai import (
    AIMessage,
    AIRequest,
    ConnectionResult,
    ErrorClass,
    ProviderConfig,
    ProviderError,
    TokenUsage,
    UsageSource,
)
from ningx.providers.base import (
    UnconfiguredProvider,
    call_with_retries,
    estimate_tokens,
    retry_delays,
)
from ningx.providers.catalogue import PROFILES, implemented_kinds, profile_for
from ningx.providers.gemini import GeminiProvider
from ningx.security.secret_store import InMemorySecretStore

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------- fixtures


@dataclass
class FakeModelEntry:
    name: str
    display_name: str | None = None
    input_token_limit: int | None = None
    output_token_limit: int | None = None


@dataclass
class FakePart:
    text: str | None


@dataclass
class FakeContent:
    parts: list[FakePart]


@dataclass
class FakeCandidate:
    content: FakeContent
    finish_reason: object = "STOP"


@dataclass
class FakeUsage:
    prompt_token_count: int | None = 120
    candidates_token_count: int | None = 40
    thoughts_token_count: int | None = None


@dataclass
class FakeResponse:
    candidates: list[FakeCandidate] = field(default_factory=list)
    usage_metadata: FakeUsage | None = None
    model_version: str | None = None


class FakeModels:
    def __init__(
        self,
        entries: list[FakeModelEntry] | None = None,
        *,
        list_error: BaseException | None = None,
        response: FakeResponse | None = None,
        errors: list[BaseException | None] | None = None,
    ) -> None:
        self.entries = entries or []
        self.list_error = list_error
        self.response = response
        self.errors = list(errors or [])
        self.list_calls = 0
        self.generate_calls: list[dict[str, object]] = []

    def list(self, config: dict[str, object] | None = None) -> list[FakeModelEntry]:
        self.list_calls += 1
        if self.list_error is not None:
            raise self.list_error
        return list(self.entries)

    def generate_content(
        self, *, model: str, contents: object, config: object
    ) -> FakeResponse:
        self.generate_calls.append({"model": model, "contents": contents, "config": config})
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        assert self.response is not None, "test did not provide a response"
        return self.response


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


def config(**overrides: object) -> ProviderConfig:
    base: dict[str, object] = {
        "provider_id": "gemini",
        "name": "Gemini",
        "kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "secret_ref": "provider/gemini",
        "max_retries": 2,
        "timeout_s": 30.0,
    }
    base.update(overrides)
    return ProviderConfig.model_validate(base)


def provider(
    models: FakeModels,
    *,
    secrets: InMemorySecretStore | None = None,
    clock: object = None,
    **overrides: object,
) -> GeminiProvider:
    store = secrets if secrets is not None else InMemorySecretStore()
    if secrets is None:
        store.set("provider/gemini", "test-key")
    ticks = clock or (lambda: START)
    return GeminiProvider(
        config(**overrides),
        store,
        client_factory=lambda key, timeout_ms: FakeClient(models),
        sleep=lambda seconds: None,
        clock=ticks,  # type: ignore[arg-type]
    )


def request(**overrides: object) -> AIRequest:
    base: dict[str, object] = {
        "messages": (AIMessage(role="user", content="What is slow?"),),
        "system": "You are a Windows performance analyst.",
        "max_output_tokens": 256,
    }
    base.update(overrides)
    return AIRequest.model_validate(base)


# ------------------------------------------------------------------ retry policy


def test_one_attempt_means_no_retry_delay() -> None:
    assert retry_delays(0) == ()
    assert retry_delays(1) == ()


def test_backoff_is_exponential_and_bounded() -> None:
    assert retry_delays(3, base_delay_s=0.5, max_delay_s=8.0) == (0.5, 1.0)
    assert retry_delays(6, base_delay_s=0.5, max_delay_s=2.0) == (0.5, 1.0, 2.0, 2.0, 2.0)


def test_a_transient_failure_is_retried_up_to_the_configured_attempts() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def operation() -> str:
        calls["n"] += 1
        raise ProviderError(ErrorClass.SERVER, "503")

    with pytest.raises(ProviderError):
        call_with_retries(operation, attempts=3, sleep=sleeps.append)

    assert calls["n"] == 3
    assert sleeps == [0.5, 1.0]


def test_a_transient_failure_that_clears_returns_the_value() -> None:
    calls = {"n": 0}

    def operation() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise ProviderError(ErrorClass.NETWORK, "reset")
        return "ok"

    assert call_with_retries(operation, attempts=3, sleep=lambda s: None) == "ok"
    assert calls["n"] == 2


@pytest.mark.parametrize(
    "error_class",
    [ErrorClass.AUTH, ErrorClass.PERMISSION, ErrorClass.INVALID_REQUEST, ErrorClass.RATE_LIMIT],
)
def test_a_permanent_failure_is_never_retried(error_class: ErrorClass) -> None:
    calls = {"n": 0}

    def operation() -> str:
        calls["n"] += 1
        raise ProviderError(error_class, "no")

    with pytest.raises(ProviderError):
        call_with_retries(operation, attempts=5, sleep=lambda s: None)
    assert calls["n"] == 1


# ------------------------------------------------------------------- validation


def test_a_complete_configuration_validates() -> None:
    assert provider(FakeModels()).validate_config().ok


def test_validation_names_every_missing_piece() -> None:
    result = provider(FakeModels(), secret_ref=None, model_id=None).validate_config()
    assert not result.ok
    assert any("no model selected" in problem for problem in result.problems)
    assert any("no credential reference" in problem for problem in result.problems)


def test_a_reference_without_a_stored_secret_is_a_problem_not_a_crash() -> None:
    result = provider(FakeModels(), secrets=InMemorySecretStore()).validate_config()
    assert not result.ok
    assert any("not in the Windows Credential Manager" in p for p in result.problems)


def test_a_provider_of_the_wrong_kind_is_refused_at_construction() -> None:
    with pytest.raises(ValueError):
        GeminiProvider(config(kind="openai"), InMemorySecretStore())


# ------------------------------------------------------------------ connection


def test_a_connection_test_reports_what_it_actually_saw() -> None:
    models = FakeModels(
        [
            FakeModelEntry("models/gemini-2.5-flash", "Gemini 2.5 Flash", 1_048_576),
            FakeModelEntry("models/gemini-2.5-pro"),
        ]
    )
    clock = _stepping_clock(0.25)
    result = provider(models, clock=clock).test_connection()

    assert isinstance(result, ConnectionResult)
    assert result.ok
    assert result.models_seen == 2
    assert result.latency_ms == 250.0
    assert "gemini-2.5-flash" in result.detail
    assert models.list_calls == 1


def test_a_connection_test_does_not_spend_generation_tokens() -> None:
    models = FakeModels([FakeModelEntry("models/gemini-2.5-flash")])
    provider(models).test_connection()
    assert models.generate_calls == []


def test_an_auth_failure_is_reported_not_raised() -> None:
    models = FakeModels(list_error=_client_error(401, "API key not valid"))
    result = provider(models).test_connection()

    assert not result.ok
    assert result.error_class is ErrorClass.AUTH
    assert "check the stored credential" in result.detail


def test_a_missing_model_is_named_with_the_count_of_visible_models() -> None:
    models = FakeModels([FakeModelEntry("models/gemini-2.0-flash")])
    result = provider(models, model_id="gemini-9-ultra").test_connection()

    assert not result.ok
    assert result.error_class is ErrorClass.INVALID_REQUEST
    assert "gemini-9-ultra" in result.detail
    assert result.models_seen == 1


def test_a_credential_that_sees_nothing_is_not_reported_as_success() -> None:
    result = provider(FakeModels([])).test_connection()
    assert not result.ok
    assert result.error_class is ErrorClass.PERMISSION
    assert result.models_seen == 0


def test_list_models_normalizes_names_and_limits() -> None:
    models = FakeModels([FakeModelEntry("models/gemini-2.5-flash", "Flash", 1_048_576, 65_536)])
    listed = provider(models).list_models()

    assert listed[0].id == "gemini-2.5-flash"
    assert listed[0].display_name == "Flash"
    assert listed[0].input_token_limit == 1_048_576
    assert listed[0].output_token_limit == 65_536


def test_a_transient_listing_failure_is_retried() -> None:
    models = FakeModels([FakeModelEntry("models/gemini-2.5-flash")])
    provider_under_test = provider(models)
    attempts = {"n": 0}
    original = models.list

    def flaky(config: dict[str, object] | None = None) -> list[FakeModelEntry]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _server_error(503, "backend unavailable")
        return original(config)

    models.list = flaky  # type: ignore[method-assign]
    assert provider_under_test.list_models()[0].id == "gemini-2.5-flash"
    assert attempts["n"] == 2


# ------------------------------------------------------------------ generation


def test_generation_reports_provider_token_counts_including_thinking() -> None:
    models = FakeModels(
        response=FakeResponse(
            candidates=[FakeCandidate(FakeContent([FakePart("Use the Optimization Center.")]))],
            usage_metadata=FakeUsage(120, 40, 7),
            model_version="gemini-2.5-flash-001",
        )
    )
    response = provider(models).generate(request())

    assert response.text == "Use the Optimization Center."
    assert response.usage.source is UsageSource.PROVIDER
    assert response.usage.input_tokens == 120
    # Thinking tokens are billed as output, so they are counted as output.
    assert response.usage.output_tokens == 47
    assert response.usage.total == 167
    assert response.model == "gemini-2.5-flash-001"
    assert response.kind == "gemini"


def test_missing_usage_metadata_is_unavailable_not_zero() -> None:
    models = FakeModels(
        response=FakeResponse(candidates=[FakeCandidate(FakeContent([FakePart("hi")]))])
    )
    response = provider(models).generate(request())

    assert response.usage.source is UsageSource.UNAVAILABLE
    assert response.usage.input_tokens is None
    assert response.usage.total is None
    assert not response.usage.known


def test_a_truncated_answer_says_length_rather_than_stop() -> None:
    models = FakeModels(
        response=FakeResponse(
            candidates=[
                FakeCandidate(FakeContent([FakePart("partial")]), finish_reason="MAX_TOKENS")
            ]
        )
    )
    response = provider(models).generate(request())

    assert response.finish_reason == "length"
    assert response.provider_finish_reason == "MAX_TOKENS"


def test_a_blocked_answer_is_reported_as_blocked() -> None:
    models = FakeModels(
        response=FakeResponse(
            candidates=[FakeCandidate(FakeContent([FakePart("")]), finish_reason="SAFETY")]
        )
    )
    assert provider(models).generate(request()).finish_reason == "blocked"


def test_an_empty_response_with_no_finish_reason_is_an_error() -> None:
    models = FakeModels(response=FakeResponse(candidates=[]))
    with pytest.raises(ProviderError) as caught:
        provider(models).generate(request())
    assert caught.value.error_class is ErrorClass.SERVER


def test_the_request_carries_the_system_instruction_and_output_cap() -> None:
    models = FakeModels(
        response=FakeResponse(candidates=[FakeCandidate(FakeContent([FakePart("x")]))])
    )
    provider(models).generate(request())
    sent = models.generate_calls[0]

    assert sent["model"] == "gemini-2.5-flash"
    config_sent = sent["config"]
    assert getattr(config_sent, "system_instruction", None) == (
        "You are a Windows performance analyst."
    )
    assert getattr(config_sent, "max_output_tokens", None) == 256


# --------------------------------------------------------------- error mapping


def test_authentication_failures_are_classified_and_not_retried() -> None:
    models = FakeModels(errors=[_client_error(401, "API key not valid")])
    with pytest.raises(ProviderError) as caught:
        provider(models).generate(request())

    assert caught.value.error_class is ErrorClass.AUTH
    assert not caught.value.retryable
    assert len(models.generate_calls) == 1


def test_rate_limiting_is_not_retried_because_it_spends_the_users_quota() -> None:
    models = FakeModels(errors=[_client_error(429, "quota exceeded")])
    with pytest.raises(ProviderError) as caught:
        provider(models).generate(request())

    assert caught.value.error_class is ErrorClass.RATE_LIMIT
    assert not caught.value.retryable
    assert len(models.generate_calls) == 1


def test_a_server_error_is_retried_then_succeeds() -> None:
    models = FakeModels(
        response=FakeResponse(candidates=[FakeCandidate(FakeContent([FakePart("ok")]))]),
        errors=[_server_error(503, "unavailable"), None],
    )
    response = provider(models).generate(request())

    assert response.text == "ok"
    assert len(models.generate_calls) == 2


def test_a_timeout_is_classified_as_retryable() -> None:
    models = FakeModels(errors=[httpx.ConnectTimeout("timed out")] * 3)
    with pytest.raises(ProviderError) as caught:
        provider(models).generate(request())

    assert caught.value.error_class is ErrorClass.TIMEOUT
    assert caught.value.retryable
    assert len(models.generate_calls) == 3


def test_an_error_message_can_never_carry_the_key_into_a_log() -> None:
    leaked = "AIzaSyD-abcdefghijklmnopqrstuvwxyz012345"
    models = FakeModels(errors=[_client_error(400, f"bad request for key {leaked}")])
    with pytest.raises(ProviderError) as caught:
        provider(models).generate(request())

    assert leaked not in caught.value.detail
    assert leaked not in str(caught.value)


# ------------------------------------------------------------------- unconfigured


def test_an_unconfigured_provider_states_its_reason_instead_of_pretending() -> None:
    stand_in = UnconfiguredProvider(config(), "no credential is stored")

    assert not stand_in.validate_config().ok
    assert stand_in.validate_config().problems == ("no credential is stored",)
    result = stand_in.test_connection()
    assert not result.ok and result.error_class is ErrorClass.NOT_CONFIGURED
    with pytest.raises(ProviderError) as caught:
        stand_in.generate(request())
    assert caught.value.error_class is ErrorClass.NOT_CONFIGURED


# ---------------------------------------------------------------------- estimate


def test_an_estimate_is_labelled_as_an_estimate() -> None:
    estimate = provider(FakeModels()).estimate_usage(request())

    assert estimate.exact is False
    assert estimate.method == "characters/4 heuristic"
    assert estimate.input_tokens > 0


def test_the_heuristic_never_returns_zero_for_empty_input() -> None:
    assert estimate_tokens("") == 1


# --------------------------------------------------------------------- catalogue


def test_every_supported_kind_has_a_profile() -> None:
    assert set(PROFILES) == {
        "gemini",
        "openai",
        "anthropic",
        "groq",
        "nvidia",
        "ollama",
        "openrouter",
        "opencode_zen",
        "cloudflare_gateway",
        "custom_openai",
    }


def test_only_gemini_is_implemented_in_this_build() -> None:
    assert implemented_kinds() == ("gemini",)


def test_unbuilt_providers_say_so_rather_than_looking_available() -> None:
    for kind, profile in PROFILES.items():
        if profile.implemented:
            continue
        assert "not built yet" in profile.note or "must be confirmed" in profile.note, kind


def test_the_local_provider_is_marked_local_and_needs_no_secret() -> None:
    ollama = profile_for("ollama")
    assert ollama.is_local
    assert not ollama.needs_secret


# ------------------------------------------------------------- config hardening


def test_a_raw_api_key_cannot_be_stored_as_a_reference() -> None:
    with pytest.raises(ValueError, match="looks like a credential"):
        config(secret_ref="AIzaSyD-abcdefghijklmnopqrstuvwxyz012345")  # noqa: S106


def test_a_remote_provider_must_use_https() -> None:
    with pytest.raises(ValueError, match="must use https"):
        config(base_url="http://models.example.com/v1")


def test_a_loopback_endpoint_may_use_plain_http() -> None:
    assert config(base_url="http://127.0.0.1:11434", is_local=True).base_url is not None


def test_a_non_http_url_is_refused() -> None:
    with pytest.raises(ValueError, match="http"):
        config(base_url="ftp://example.com")


def test_usage_marked_unavailable_cannot_carry_counts() -> None:
    with pytest.raises(ValueError, match="cannot carry token counts"):
        TokenUsage(input_tokens=10, source=UsageSource.UNAVAILABLE)


def test_provider_usage_must_carry_at_least_one_count() -> None:
    with pytest.raises(ValueError, match="at least one token count"):
        TokenUsage(source=UsageSource.PROVIDER)


# ----------------------------------------------------------------------- helpers


def _stepping_clock(step_s: float) -> object:
    """A clock that advances on every read, so latency is deterministic."""
    state = {"now": START}

    def read() -> datetime:
        state["now"] = state["now"] + timedelta(seconds=step_s)
        return state["now"]

    return read


def _client_error(code: int, message: str) -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"message": message}}, None)


def _server_error(code: int, message: str) -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"message": message}}, None)
