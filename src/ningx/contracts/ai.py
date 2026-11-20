"""AI provider contracts.

These types are the boundary between NingX and every language model. Three rules
are encoded here rather than left to convention:

* **A number is either reported or absent.** :class:`TokenUsage` cannot carry a
  count while claiming the source is ``unavailable``; a missing token count is
  ``None``, never zero and never an estimate presented as fact.
* **A failure is classified.** :class:`ProviderError` carries an
  :class:`ErrorClass` and an explicit ``retryable`` flag, so a caller cannot
  retry an authentication or quota failure by accident.
* **A capability is declared.** :class:`ProviderCapabilities` lets the UI say
  "this provider does not report token usage" instead of showing a dash that
  could be read as zero.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ningx.contracts.action import JsonValue
from ningx.contracts.time import ensure_utc
from ningx.observability.redaction import contains_secret

_FROZEN = ConfigDict(extra="forbid", frozen=True)

# Provider kinds are a closed list: adding one is a code change with a test, not
# a configuration string the user can type.
ProviderKind = Literal[
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
]

PROVIDER_KINDS: tuple[ProviderKind, ...] = (
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
)


class UsageSource(StrEnum):
    """Where a token count came from.

    ``PROVIDER`` means the provider reported it. ``UNAVAILABLE`` means it did
    not, and NingX refuses to invent one.
    """

    PROVIDER = "provider"
    UNAVAILABLE = "unavailable"


class ErrorClass(StrEnum):
    """Normalized failure classes, mapped from provider-specific errors."""

    NOT_CONFIGURED = "not_configured"
    AUTH = "auth"
    PERMISSION = "permission"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    SERVER = "server"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return _ERROR_LABELS[self]

    @property
    def retryable(self) -> bool:
        """Only transient classes may be retried.

        Rate limiting is deliberately *not* retryable: repeating a request that
        the provider has already refused spends the user's quota without new
        information. The UI offers a manual retry instead, with the provider's
        own ``retry_after_s`` when it sent one.
        """
        return self in _RETRYABLE


_RETRYABLE = frozenset(
    {
        ErrorClass.TIMEOUT,
        ErrorClass.NETWORK,
        ErrorClass.SERVER,
    }
)

_ERROR_LABELS = {
    ErrorClass.NOT_CONFIGURED: "not configured",
    ErrorClass.AUTH: "authentication failed",
    ErrorClass.PERMISSION: "permission denied",
    ErrorClass.INVALID_REQUEST: "invalid request",
    ErrorClass.RATE_LIMIT: "rate limited",
    ErrorClass.TIMEOUT: "timed out",
    ErrorClass.NETWORK: "network error",
    ErrorClass.SERVER: "provider error",
    ErrorClass.UNSUPPORTED: "not supported by this provider",
    ErrorClass.UNKNOWN: "unclassified error",
}


class ProviderCapabilities(BaseModel):
    """What a provider adapter actually supports.

    Nothing is assumed: a flag is ``True`` only where the adapter has a tested
    code path for it.
    """

    model_config = _FROZEN

    tool_calling: bool = False
    json_mode: bool = False
    streaming: bool = False
    usage_metadata: bool = False
    model_listing: bool = False
    system_instruction: bool = False
    input_token_limit: int | None = Field(default=None, ge=0)


class ModelInfo(BaseModel):
    model_config = _FROZEN

    id: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, max_length=256)
    input_token_limit: int | None = Field(default=None, ge=0)
    output_token_limit: int | None = Field(default=None, ge=0)


class TokenUsage(BaseModel):
    """Token counts, or an honest statement that they were not reported."""

    model_config = _FROZEN

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    source: UsageSource = UsageSource.UNAVAILABLE

    @model_validator(mode="after")
    def _source_matches_counts(self) -> TokenUsage:
        counts_present = self.input_tokens is not None or self.output_tokens is not None
        if self.source is UsageSource.UNAVAILABLE and counts_present:
            raise ValueError(
                "usage marked unavailable cannot carry token counts; "
                "label reported counts as provider usage"
            )
        if self.source is UsageSource.PROVIDER and not counts_present:
            raise ValueError("provider usage must carry at least one token count")
        return self

    @property
    def total(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)

    @property
    def known(self) -> bool:
        return self.source is UsageSource.PROVIDER


UNKNOWN_USAGE = TokenUsage()


class UsageEstimate(BaseModel):
    """A pre-flight estimate, explicitly labelled as one.

    Kept separate from :class:`TokenUsage` on purpose: an estimate is a guess
    about a request that has not run, and must never be recorded as a measured
    token count.
    """

    model_config = _FROZEN

    input_tokens: int = Field(ge=0)
    method: str = Field(min_length=1, max_length=120)
    exact: bool = False


class AIMessage(BaseModel):
    model_config = _FROZEN

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=200_000)


class AIRequest(BaseModel):
    """A typed request. No provider-specific fields leak in here."""

    model_config = _FROZEN

    messages: Annotated[tuple[AIMessage, ...], Field(min_length=1)]
    system: str | None = Field(default=None, max_length=50_000)
    model: str | None = Field(default=None, max_length=256)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1, le=65_536)
    json_schema: dict[str, JsonValue] | None = None
    task: str = Field(default="unspecified", max_length=64)


class AIResponse(BaseModel):
    model_config = _FROZEN

    provider_id: str = Field(min_length=1, max_length=128)
    kind: ProviderKind
    model: str = Field(min_length=1, max_length=256)
    text: str
    latency_ms: float = Field(ge=0.0)
    usage: TokenUsage = UNKNOWN_USAGE
    finish_reason: str = Field(default="unknown", max_length=64)
    provider_finish_reason: str | None = Field(default=None, max_length=64)


class ValidationResult(BaseModel):
    model_config = _FROZEN

    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


class ConnectionResult(BaseModel):
    """The outcome of a real connection test, not a guess from configuration."""

    model_config = _FROZEN

    ok: bool
    detail: str = Field(default="", max_length=2000)
    latency_ms: float | None = Field(default=None, ge=0.0)
    error_class: ErrorClass | None = None
    models_seen: int | None = Field(default=None, ge=0)
    retry_after_s: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def _outcome_is_consistent(self) -> ConnectionResult:
        if self.ok and self.error_class is not None:
            raise ValueError("a successful connection test cannot carry an error class")
        if not self.ok and self.error_class is None:
            raise ValueError("a failed connection test must name its error class")
        return self


class ProviderConfig(BaseModel):
    """Non-secret provider configuration.

    The credential itself never appears here: ``secret_ref`` names an entry in
    the OS secret store. A value that looks like a credential is rejected rather
    than stored, because the failure mode of accepting it is a plaintext key in
    the database.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=128)
    kind: ProviderKind
    enabled: bool = True
    is_local: bool = False
    base_url: str | None = Field(default=None, max_length=2048)
    model_id: str | None = Field(default=None, max_length=256)
    auth_scheme: str | None = Field(default=None, max_length=64)
    timeout_s: float = Field(default=60.0, ge=1.0, le=600.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_output_tokens: int | None = Field(default=None, ge=1, le=65_536)
    priority: int = Field(default=100, ge=0, le=10_000)
    fallback_ok: bool = False
    secret_ref: str | None = Field(default=None, max_length=200)
    extra: dict[str, JsonValue] = Field(default_factory=dict)
    last_test_at: datetime | None = None
    last_test_status: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _no_plaintext_credential(self) -> ProviderConfig:
        if self.secret_ref is not None:
            if contains_secret(self.secret_ref):
                raise ValueError(
                    "secret_ref looks like a credential; store the value with "
                    "SecretStore and pass its reference instead"
                )
            if len(self.secret_ref) > 80:
                raise ValueError("secret_ref must be a short reference, not a key")
        if self.base_url is not None:
            scheme = self.base_url.split("://", 1)[0].lower()
            if "://" not in self.base_url or scheme not in {"http", "https"}:
                raise ValueError("base_url must be an http(s) URL")
        return self

    @model_validator(mode="after")
    def _local_providers_need_no_public_tls(self) -> ProviderConfig:
        # A local server is expected to be plain HTTP on loopback; a remote
        # endpoint over plain HTTP would send a bearer token in the clear.
        if self.base_url is None or self.is_local:
            return self
        if self.base_url.lower().startswith("http://") and not _is_loopback(self.base_url):
            raise ValueError("a remote provider must use https")
        return self

    @field_validator("last_test_at")
    @classmethod
    def _timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_utc(value)


def _is_loopback(url: str) -> bool:
    host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return host in {"localhost", "127.0.0.1", "::1", "[::1]"}


class ProviderError(Exception):
    """A classified provider failure. Carries enough for the UI to be honest."""

    def __init__(
        self,
        error_class: ErrorClass,
        detail: str = "",
        *,
        retry_after_s: float | None = None,
        status_code: int | None = None,
    ) -> None:
        self.error_class = error_class
        self.detail = detail
        self.retry_after_s = retry_after_s
        self.status_code = status_code
        super().__init__(f"{error_class.value}: {detail}" if detail else error_class.value)

    @property
    def retryable(self) -> bool:
        return self.error_class.retryable

    def user_message(self) -> str:
        """One sentence a user can act on. Never includes the credential."""
        message = self.error_class.label
        if self.error_class is ErrorClass.AUTH:
            message += " — check the stored credential for this provider"
        elif self.error_class is ErrorClass.RATE_LIMIT:
            message += (
                f" — the provider asked to wait {self.retry_after_s:.0f}s"
                if self.retry_after_s
                else " — try again later"
            )
        elif self.error_class is ErrorClass.NOT_CONFIGURED:
            message += " — add a credential on the AI Providers screen"
        return message if not self.detail else f"{message} ({self.detail})"


__all__ = [
    "PROVIDER_KINDS",
    "UNKNOWN_USAGE",
    "AIMessage",
    "AIRequest",
    "AIResponse",
    "ConnectionResult",
    "ErrorClass",
    "ModelInfo",
    "ProviderCapabilities",
    "ProviderConfig",
    "ProviderError",
    "ProviderKind",
    "TokenUsage",
    "UsageEstimate",
    "UsageSource",
    "ValidationResult",
]
