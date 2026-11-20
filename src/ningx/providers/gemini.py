"""Google Gemini adapter, built on the official ``google-genai`` SDK.

Three deliberate choices:

* **The SDK does not retry.** ``HttpRetryOptions(attempts=1)`` turns its retry
  loop off and :func:`ningx.providers.base.call_with_retries` applies this
  application's policy instead, so ``max_retries`` in the configuration means
  what it says and one request cannot quietly become six.
* **A connection test is a real request.** It lists the models the credential
  can see and checks the configured model is among them. It does not spend
  generation tokens, and it reports the model count so a user can tell an empty
  key from a working one.
* **Thinking tokens are counted as output.** Gemini bills reasoning tokens as
  output; reporting only ``candidates_token_count`` would understate cost.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from importlib.util import find_spec
from typing import Any

import httpx

from ningx.contracts.ai import (
    AIRequest,
    AIResponse,
    ConnectionResult,
    ErrorClass,
    ModelInfo,
    ProviderCapabilities,
    ProviderConfig,
    ProviderError,
    TokenUsage,
    UsageEstimate,
    UsageSource,
    ValidationResult,
)
from ningx.contracts.time import utcnow
from ningx.observability.redaction import redact_text
from ningx.providers.base import call_with_retries, estimate_tokens
from ningx.providers.catalogue import profile_for

_MODEL_PREFIX = "models/"
_MAX_DETAIL = 300

# Normalized finish reasons. The raw provider value is kept alongside so a user
# can see exactly what Gemini said.
_FINISH = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "blocked",
    "RECITATION": "blocked",
    "BLOCKLIST": "blocked",
    "PROHIBITED_CONTENT": "blocked",
    "SPII": "blocked",
    "MALFORMED_FUNCTION_CALL": "error",
    "OTHER": "other",
}

# A client factory takes (api_key, timeout_ms) and returns an object with a
# `.models` attribute. Injected in tests so no test can reach the network.
ClientFactory = Callable[[str, int], Any]


class GeminiProvider:
    """A real Gemini adapter. It reads a key from the secret store, never a file."""

    def __init__(
        self,
        config: ProviderConfig,
        secrets: Any,
        *,
        client_factory: ClientFactory | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        if config.kind != "gemini":
            raise ValueError(f"GeminiProvider cannot serve kind {config.kind!r}")
        self._config = config
        self._secrets = secrets
        self._client_factory = client_factory
        self._sleep = sleep
        self._clock = clock

    # ------------------------------------------------------------------ identity

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def capabilities(self) -> ProviderCapabilities:
        return profile_for("gemini").capabilities

    # ----------------------------------------------------------------- validation

    def validate_config(self) -> ValidationResult:
        problems: list[str] = []
        if self._config.kind != "gemini":
            problems.append("configuration kind is not gemini")
        if not self._config.model_id:
            problems.append("no model selected")
        if not self._config.secret_ref:
            problems.append("no credential reference configured")
        elif self._read_secret() is None:
            problems.append(
                f"credential {self._config.secret_ref!r} is not in the Windows "
                "Credential Manager"
            )
        if not _sdk_available() and self._client_factory is None:
            problems.append("the google-genai package is not installed")
        return ValidationResult(problems=tuple(problems))

    # ------------------------------------------------------------------- network

    def test_connection(self) -> ConnectionResult:
        started = self._clock()
        try:
            models = self._list_models_once()
        except ProviderError as exc:
            return ConnectionResult(
                ok=False,
                detail=exc.user_message(),
                latency_ms=_elapsed_ms(started, self._clock()),
                error_class=exc.error_class,
                retry_after_s=exc.retry_after_s,
            )

        wanted = _bare_model(self._config.model_id or "")
        ids = {_bare_model(model.id) for model in models}
        latency = _elapsed_ms(started, self._clock())
        if not models:
            return ConnectionResult(
                ok=False,
                detail="the credential is valid but exposes no models",
                latency_ms=latency,
                error_class=ErrorClass.PERMISSION,
                models_seen=0,
            )
        if wanted and wanted not in ids:
            return ConnectionResult(
                ok=False,
                detail=(
                    f"model {wanted!r} is not available to this credential; "
                    f"{len(models)} models are visible"
                ),
                latency_ms=latency,
                error_class=ErrorClass.INVALID_REQUEST,
                models_seen=len(models),
            )
        return ConnectionResult(
            ok=True,
            detail=(
                f"credential valid; {len(models)} models visible"
                + (f"; {wanted} available" if wanted else "")
            ),
            latency_ms=latency,
            models_seen=len(models),
        )

    def list_models(self) -> list[ModelInfo]:
        return call_with_retries(
            self._list_models_once,
            attempts=self._attempts(),
            sleep=self._sleep,
        )

    def generate(self, request: AIRequest) -> AIResponse:
        if request.json_schema is not None and not self.capabilities.json_mode:
            raise ProviderError(
                ErrorClass.UNSUPPORTED, "this adapter cannot request JSON output"
            )
        model = request.model or self._config.model_id
        if not model:
            raise ProviderError(ErrorClass.NOT_CONFIGURED, "no model selected")

        started = self._clock()
        response = call_with_retries(
            lambda: self._generate_once(request, model),
            attempts=self._attempts(),
            sleep=self._sleep,
        )
        return self._to_response(response, model, _elapsed_ms(started, self._clock()))

    def estimate_usage(self, request: AIRequest) -> UsageEstimate:
        characters = sum(len(message.content) for message in request.messages)
        characters += len(request.system or "")
        return UsageEstimate(
            input_tokens=estimate_tokens("x" * characters),
            method="characters/4 heuristic",
            exact=False,
        )

    # ------------------------------------------------------------------- internals

    def _attempts(self) -> int:
        return self._config.max_retries + 1

    def _read_secret(self) -> str | None:
        reference = self._config.secret_ref
        if not reference:
            return None
        try:
            value = self._secrets.get(reference)
        except Exception as exc:
            raise ProviderError(
                ErrorClass.NOT_CONFIGURED,
                f"the credential store could not be read: {type(exc).__name__}",
            ) from None
        return value if isinstance(value, str) and value else None

    def _client(self) -> Any:
        if self._client_factory is not None:
            injected_key = self._read_secret() or "test-key"
            return self._client_factory(injected_key, int(self._config.timeout_s * 1000))

        secret = self._read_secret()
        if not secret:
            raise ProviderError(
                ErrorClass.NOT_CONFIGURED,
                "no credential is stored for this provider",
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError:  # pragma: no cover - dependency is installed in dev
            raise ProviderError(
                ErrorClass.UNSUPPORTED, "the google-genai package is not installed"
            ) from None

        return genai.Client(
            api_key=secret,
            http_options=types.HttpOptions(
                timeout=int(self._config.timeout_s * 1000),
                # This application owns the retry policy; see the module docstring.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def _list_models_once(self) -> list[ModelInfo]:
        client = self._client()
        try:
            page = client.models.list(config={"page_size": 100})
            models: list[ModelInfo] = []
            for entry in page:
                name = getattr(entry, "name", None)
                if not isinstance(name, str) or not name:
                    continue
                models.append(
                    ModelInfo(
                        id=_bare_model(name),
                        display_name=getattr(entry, "display_name", None),
                        input_token_limit=_optional_int(
                            getattr(entry, "input_token_limit", None)
                        ),
                        output_token_limit=_optional_int(
                            getattr(entry, "output_token_limit", None)
                        ),
                    )
                )
        except Exception as exc:
            raise _map_exception(exc) from None
        return models

    def _generate_once(self, request: AIRequest, model: str) -> Any:
        client = self._client()
        try:
            from google.genai import types
        except ImportError:  # pragma: no cover
            raise ProviderError(
                ErrorClass.UNSUPPORTED, "the google-genai package is not installed"
            ) from None

        contents = [
            types.Content(
                role="model" if message.role == "assistant" else "user",
                parts=[types.Part(text=message.content)],
            )
            for message in request.messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens or self._config.max_output_tokens,
            response_mime_type="application/json" if request.json_schema else None,
            response_json_schema=request.json_schema,
        )
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            raise _map_exception(exc) from None

    def _to_response(self, response: Any, model: str, latency_ms: float) -> AIResponse:
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None

        text = ""
        if candidate is not None:
            parts = getattr(getattr(candidate, "content", None), "parts", None) or []
            text = "".join(
                part.text for part in parts if isinstance(getattr(part, "text", None), str)
            )

        raw_finish = getattr(candidate, "finish_reason", None) if candidate else None
        raw_name = getattr(raw_finish, "name", None) or (
            str(raw_finish) if raw_finish is not None else None
        )
        finish = _FINISH.get(raw_name or "", "unknown")

        metadata = getattr(response, "usage_metadata", None)
        usage = _usage_from(metadata)
        if not text and finish == "unknown":
            # A response with neither text nor a finish reason is not a success.
            raise ProviderError(ErrorClass.SERVER, "the provider returned no content")

        return AIResponse(
            provider_id=self._config.provider_id,
            kind="gemini",
            model=str(getattr(response, "model_version", None) or model),
            text=text,
            latency_ms=latency_ms,
            usage=usage,
            finish_reason=finish,
            provider_finish_reason=raw_name,
        )


def _usage_from(metadata: Any) -> TokenUsage:
    if metadata is None:
        return TokenUsage()
    prompt = _optional_int(getattr(metadata, "prompt_token_count", None))
    candidates = _optional_int(getattr(metadata, "candidates_token_count", None))
    thoughts = _optional_int(getattr(metadata, "thoughts_token_count", None))
    output = None
    if candidates is not None or thoughts is not None:
        output = (candidates or 0) + (thoughts or 0)
    if prompt is None and output is None:
        return TokenUsage()
    return TokenUsage(
        input_tokens=prompt,
        output_tokens=output,
        source=UsageSource.PROVIDER,
    )


def _map_exception(exc: BaseException) -> ProviderError:
    """Translate an SDK/transport failure into a classified, redacted error."""
    detail = redact_text(str(exc))[:_MAX_DETAIL]

    sdk_errors = _sdk_errors()
    if sdk_errors is not None:
        if isinstance(exc, sdk_errors.ClientError):
            code = _status_code(exc)
            return ProviderError(_client_class(code), detail, status_code=code)
        if isinstance(exc, sdk_errors.ServerError):
            return ProviderError(ErrorClass.SERVER, detail, status_code=_status_code(exc))
        if isinstance(exc, sdk_errors.APIError):
            code = _status_code(exc)
            return ProviderError(
                ErrorClass.SERVER if code >= 500 else ErrorClass.UNKNOWN,
                detail,
                status_code=code,
            )

    if isinstance(exc, httpx.TimeoutException | TimeoutError):
        return ProviderError(ErrorClass.TIMEOUT, detail)
    if isinstance(exc, httpx.TransportError | ConnectionError | OSError):
        return ProviderError(ErrorClass.NETWORK, detail)
    return ProviderError(ErrorClass.UNKNOWN, detail or type(exc).__name__)


def _sdk_errors() -> Any:
    """The SDK's error module, or ``None`` when the optional package is absent."""
    try:
        from google.genai import errors
    except ImportError:  # pragma: no cover - installed in dev
        return None
    return errors


def _client_class(code: int) -> ErrorClass:
    if code == 401:
        return ErrorClass.AUTH
    if code == 403:
        return ErrorClass.PERMISSION
    if code == 408:
        return ErrorClass.TIMEOUT
    if code == 429:
        return ErrorClass.RATE_LIMIT
    if 400 <= code < 500:
        return ErrorClass.INVALID_REQUEST
    return ErrorClass.UNKNOWN


def _status_code(exc: BaseException) -> int:
    for attribute in ("code", "status_code"):
        value = getattr(exc, attribute, None)
        if isinstance(value, int):
            return value
    return 0


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _bare_model(name: str) -> str:
    return name[len(_MODEL_PREFIX) :] if name.startswith(_MODEL_PREFIX) else name


def _elapsed_ms(started: datetime, finished: datetime) -> float:
    return max(0.0, (finished - started).total_seconds() * 1000.0)


def _sdk_available() -> bool:
    return find_spec("google.genai") is not None


__all__ = ["ClientFactory", "GeminiProvider"]
