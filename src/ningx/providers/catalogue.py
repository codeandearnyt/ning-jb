"""Provider catalogue: what each supported provider kind actually is.

This table is the honest inventory. ``implemented`` says whether an adapter
exists in this build; a provider whose row says ``implemented=False`` cannot be
connection-tested, and the UI must say so instead of offering a button that
fails. Adding an adapter flips one flag and adds its tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ningx.contracts.ai import PROVIDER_KINDS, ProviderCapabilities, ProviderKind


@dataclass(frozen=True)
class ProviderProfile:
    kind: ProviderKind
    label: str
    is_local: bool
    needs_secret: bool
    implemented: bool
    auth_scheme: str
    default_base_url: str | None
    capabilities: ProviderCapabilities
    note: str


_GEMINI = ProviderProfile(
    kind="gemini",
    label="Google Gemini",
    is_local=False,
    needs_secret=True,
    implemented=True,
    auth_scheme="api_key",
    default_base_url=None,
    # The SDK can do tool calling and streaming, but this adapter does not wire
    # either. Declaring them would let the UI offer a feature that is not there.
    capabilities=ProviderCapabilities(
        json_mode=True,
        usage_metadata=True,
        model_listing=True,
        system_instruction=True,
    ),
    note="Adapter built on the official google-genai SDK.",
)


def _unbuilt(
    kind: ProviderKind,
    label: str,
    *,
    is_local: bool = False,
    needs_secret: bool = True,
    note: str,
) -> ProviderProfile:
    return ProviderProfile(
        kind=kind,
        label=label,
        is_local=is_local,
        needs_secret=needs_secret,
        implemented=False,
        auth_scheme="api_key",
        default_base_url=None,
        capabilities=ProviderCapabilities(),
        note=note,
    )


PROFILES: Mapping[ProviderKind, ProviderProfile] = MappingProxyType(
    {
        "gemini": _GEMINI,
        "openai": _unbuilt("openai", "OpenAI", note="Adapter not built yet (M4.1)."),
        "anthropic": _unbuilt(
            "anthropic", "Anthropic Claude", note="Adapter not built yet (M4.1)."
        ),
        "groq": _unbuilt("groq", "Groq", note="Adapter not built yet (M4.1)."),
        "nvidia": _unbuilt("nvidia", "NVIDIA", note="Adapter not built yet (M4.1)."),
        "ollama": _unbuilt(
            "ollama",
            "Ollama (local)",
            is_local=True,
            needs_secret=False,
            note="Adapter not built yet (M4.1). Runs on this machine; no data leaves it.",
        ),
        "openrouter": _unbuilt("openrouter", "OpenRouter", note="Adapter not built yet (M4.1)."),
        "opencode_zen": _unbuilt(
            "opencode_zen",
            "OpenCode Zen",
            note="Adapter not built yet; its authentication contract must be confirmed first.",
        ),
        "cloudflare_gateway": _unbuilt(
            "cloudflare_gateway",
            "Cloudflare AI Gateway",
            note=(
                "Adapter not built yet. A gateway is a route to a model, not a model "
                "family, so it needs its own configuration shape (M4.2)."
            ),
        ),
        "custom_openai": _unbuilt(
            "custom_openai",
            "Custom OpenAI-compatible endpoint",
            note="Adapter not built yet (M4.1).",
        ),
    }
)

assert set(PROFILES) == set(PROVIDER_KINDS), "every provider kind needs a profile"


def profile_for(kind: ProviderKind) -> ProviderProfile:
    return PROFILES[kind]


def implemented_kinds() -> tuple[ProviderKind, ...]:
    return tuple(kind for kind, profile in PROFILES.items() if profile.implemented)


__all__ = [
    "PROFILES",
    "ProviderProfile",
    "implemented_kinds",
    "profile_for",
]
