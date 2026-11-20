"""Windows Credential Manager backed secret storage.

API keys never live in configuration files, logs, or the database. The database
stores a *reference* (``provider/gemini``); the value lives in Credential
Manager under a namespaced target name.
"""

from __future__ import annotations

import os
from typing import Protocol

DEFAULT_TARGET_PREFIX = "NingX-Optimizer/"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class SecretStoreError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class SecretStore(Protocol):
    def set(self, reference: str, secret: str) -> None: ...

    def get(self, reference: str) -> str | None: ...

    def delete(self, reference: str) -> bool: ...

    def exists(self, reference: str) -> bool: ...


def _validate_reference(reference: str) -> str:
    cleaned = reference.strip()
    if not cleaned or len(cleaned) > 200:
        raise SecretStoreError("secret.invalid_reference", "reference must be 1-200 chars")
    if any(ch in cleaned for ch in "\x00\r\n"):
        raise SecretStoreError("secret.invalid_reference", "control characters not allowed")
    return cleaned


class WindowsCredentialStore:
    """Stores secrets in the per-user Windows Credential Manager vault."""

    def __init__(self, *, prefix: str = DEFAULT_TARGET_PREFIX) -> None:
        if os.name != "nt":
            raise SecretStoreError("secret.unsupported_platform")
        self._prefix = prefix

    def _target(self, reference: str) -> str:
        return f"{self._prefix}{_validate_reference(reference)}"

    def set(self, reference: str, secret: str) -> None:
        if not secret:
            raise SecretStoreError("secret.empty_value")
        import win32cred

        blob = {
            "Type": _CRED_TYPE_GENERIC,
            "TargetName": self._target(reference),
            "UserName": "ningx",
            "CredentialBlob": secret,
            "Comment": "NingX-Optimizer provider credential",
            "Persist": _CRED_PERSIST_LOCAL_MACHINE,
        }
        try:
            win32cred.CredWrite(blob, 0)
        except Exception as exc:
            raise SecretStoreError("secret.write_failed", _describe(exc)) from None

    def get(self, reference: str) -> str | None:
        import win32cred

        try:
            credential = win32cred.CredRead(self._target(reference), _CRED_TYPE_GENERIC)
        except Exception as exc:
            if _is_not_found(exc):
                return None
            raise SecretStoreError("secret.read_failed", _describe(exc)) from None
        return _decode_blob(credential.get("CredentialBlob"))

    def delete(self, reference: str) -> bool:
        import win32cred

        try:
            win32cred.CredDelete(self._target(reference), _CRED_TYPE_GENERIC)
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise SecretStoreError("secret.delete_failed", _describe(exc)) from None
        return True

    def exists(self, reference: str) -> bool:
        return self.get(reference) is not None


class InMemorySecretStore:
    """Test double. Holds secrets only for the life of the object."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set(self, reference: str, secret: str) -> None:
        if not secret:
            raise SecretStoreError("secret.empty_value")
        self._values[_validate_reference(reference)] = secret

    def get(self, reference: str) -> str | None:
        return self._values.get(_validate_reference(reference))

    def delete(self, reference: str) -> bool:
        return self._values.pop(_validate_reference(reference), None) is not None

    def exists(self, reference: str) -> bool:
        return _validate_reference(reference) in self._values


def _decode_blob(value: object) -> str | None:
    """Decode a Credential Manager blob.

    pywin32 accepts ``str`` on write but returns the raw blob as UTF-16LE
    bytes on read, so a plain ``isinstance(value, str)`` check loses every
    secret written by this application.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        for encoding in ("utf-16-le", "utf-8"):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue
    return None


def _is_not_found(exc: BaseException) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror == _ERROR_NOT_FOUND:
        return True
    args: tuple[object, ...] = getattr(exc, "args", ())
    return bool(args) and args[0] == _ERROR_NOT_FOUND


def _describe(exc: BaseException) -> str:
    winerror = getattr(exc, "winerror", None)
    name = type(exc).__name__
    return f"{name} (winerror={winerror})" if winerror is not None else name


__all__ = [
    "DEFAULT_TARGET_PREFIX",
    "InMemorySecretStore",
    "SecretStore",
    "SecretStoreError",
    "WindowsCredentialStore",
]
