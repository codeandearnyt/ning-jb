"""Secret storage: in-memory semantics and the Windows blob encoding."""

from __future__ import annotations

import os
import sys
import types

import pytest

from ningx.security.secret_store import (
    InMemorySecretStore,
    SecretStoreError,
    WindowsCredentialStore,
)

requires_windows = pytest.mark.skipif(os.name != "nt", reason="Credential Manager is Windows only")


def test_in_memory_round_trip_and_delete() -> None:
    store = InMemorySecretStore()
    assert store.get("provider/gemini") is None
    assert not store.exists("provider/gemini")

    store.set("provider/gemini", "value-123")
    assert store.get("provider/gemini") == "value-123"
    assert store.exists("provider/gemini")

    assert store.delete("provider/gemini") is True
    assert store.delete("provider/gemini") is False
    assert store.get("provider/gemini") is None


def test_empty_secret_and_invalid_reference_are_rejected() -> None:
    store = InMemorySecretStore()
    with pytest.raises(SecretStoreError) as empty:
        store.set("provider/gemini", "")
    assert empty.value.code == "secret.empty_value"

    for reference in ("", "   ", "bad\nreference", "x" * 201):
        with pytest.raises(SecretStoreError) as invalid:
            store.get(reference)
        assert invalid.value.code == "secret.invalid_reference"


@requires_windows
def test_windows_store_decodes_utf16_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    """pywin32 returns CredentialBlob as UTF-16LE bytes, not str."""
    fake = types.ModuleType("win32cred")
    written: dict[str, object] = {}

    def cred_write(blob: dict[str, object], flags: int) -> None:
        written.update(blob)

    def cred_read(target: str, cred_type: int) -> dict[str, object]:
        secret = str(written["CredentialBlob"])
        return {
            "TargetName": target,
            "UserName": "ningx",
            "CredentialBlob": secret.encode("utf-16-le"),
        }

    def cred_delete(target: str, cred_type: int) -> None:
        written.clear()

    fake.CredWrite = cred_write  # type: ignore[attr-defined]
    fake.CredRead = cred_read  # type: ignore[attr-defined]
    fake.CredDelete = cred_delete  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32cred", fake)

    store = WindowsCredentialStore()
    store.set("provider/gemini", "AIza-test-value")
    assert written["TargetName"] == "NingX-Optimizer/provider/gemini"
    assert store.get("provider/gemini") == "AIza-test-value"
    assert store.exists("provider/gemini")
    assert store.delete("provider/gemini") is True


@requires_windows
def test_windows_store_returns_none_when_the_secret_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = types.ModuleType("win32cred")

    class CredentialNotFound(Exception):
        winerror = 1168

    def cred_read(target: str, cred_type: int) -> dict[str, object]:
        raise CredentialNotFound(1168, "element not found")

    fake.CredRead = cred_read  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32cred", fake)

    assert WindowsCredentialStore().get("provider/missing") is None


@requires_windows
def test_windows_store_wraps_write_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("win32cred")

    def cred_write(blob: dict[str, object], flags: int) -> None:
        raise OSError(5, "access denied")

    fake.CredWrite = cred_write  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32cred", fake)

    with pytest.raises(SecretStoreError) as excinfo:
        WindowsCredentialStore().set("provider/gemini", "value")
    assert excinfo.value.code == "secret.write_failed"
    assert "value" not in str(excinfo.value)
