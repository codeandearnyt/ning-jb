"""Authenticode signature verification via WinVerifyTrust.

The return value is deliberately tri-state:

* ``True``  — a valid, trusted signature was found,
* ``False`` — the file is definitively unsigned,
* ``None``  — we could not decide (offline revocation check, unsupported file,
  API failure).

``None`` must never be treated as "signed". Callers that need a binary answer
should keep the conservative default.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path

_TRUST_E_NOSIGNATURE = 0x800B0100
_TRUST_E_PROVIDER_UNKNOWN = 0x800B0001
_TRUST_E_SUBJECT_FORM_UNKNOWN = 0x800B0003
_NO_SIGNATURE_CODES = frozenset(
    {_TRUST_E_NOSIGNATURE, _TRUST_E_PROVIDER_UNKNOWN, _TRUST_E_SUBJECT_FORM_UNKNOWN}
)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pcwszFilePath", wintypes.LPCWSTR),
        ("hFile", wintypes.HANDLE),
        ("pgKnownSubject", ctypes.POINTER(_GUID)),
    ]


class _WINTRUST_DATA(ctypes.Structure):
    # The native structure contains a union at pFile's offset. Declaring the
    # file branch directly is the standard ctypes approach and is layout-safe
    # because the union members all start at the same offset.
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pPolicyCallbackData", ctypes.c_void_p),
        ("pSIPClientData", ctypes.c_void_p),
        ("dwUIChoice", wintypes.DWORD),
        ("fdwRevocationChecks", wintypes.DWORD),
        ("dwUnionChoice", wintypes.DWORD),
        ("pFile", ctypes.POINTER(_WINTRUST_FILE_INFO)),
        ("dwStateAction", wintypes.DWORD),
        ("hWVTStateData", wintypes.HANDLE),
        ("pwszURLReference", wintypes.LPWSTR),
        ("dwProvFlags", wintypes.DWORD),
        ("dwUIContext", wintypes.DWORD),
        ("pSignatureSettings", ctypes.c_void_p),
    ]


def _build_action_guid() -> _GUID:
    guid = _GUID()
    guid.Data1 = 0x00AAC56B
    guid.Data2 = 0xCD44
    guid.Data3 = 0x11D0
    for index, byte in enumerate((0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE)):
        guid.Data4[index] = byte
    return guid


_ACTION_GUID = _build_action_guid()

_WTD_UI_NONE = 2
_WTD_REVOKE_NONE = 0
_WTD_CHOICE_FILE = 1
_WTD_STATEACTION_VERIFY = 0
_WTD_STATEACTION_CLOSE = 2
_WTD_CACHE_ONLY_URL_RETRIEVAL = 0x00000010

@lru_cache(maxsize=1)
def _load_wintrust() -> ctypes.WinDLL:
    library = ctypes.WinDLL("wintrust")
    library.WinVerifyTrust.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
    ]
    library.WinVerifyTrust.restype = wintypes.LONG
    return library


@lru_cache(maxsize=512)
def verify_authenticode(path: str) -> bool | None:
    """Verify the Authenticode signature of ``path``."""
    if os.name != "nt" or not path:
        return None
    if not Path(path).is_file():
        return None
    try:
        library = _load_wintrust()
    except OSError:
        return None

    file_info = _WINTRUST_FILE_INFO()
    file_info.cbStruct = ctypes.sizeof(_WINTRUST_FILE_INFO)
    file_info.pcwszFilePath = path
    file_info.hFile = None
    file_info.pgKnownSubject = None

    data = _WINTRUST_DATA()
    data.cbStruct = ctypes.sizeof(_WINTRUST_DATA)
    data.dwUIChoice = _WTD_UI_NONE
    data.fdwRevocationChecks = _WTD_REVOKE_NONE
    data.dwUnionChoice = _WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(file_info)
    data.dwStateAction = _WTD_STATEACTION_VERIFY
    data.dwProvFlags = _WTD_CACHE_ONLY_URL_RETRIEVAL

    try:
        status = library.WinVerifyTrust(
            None, ctypes.byref(_ACTION_GUID), ctypes.cast(ctypes.byref(data), ctypes.c_void_p)
        )
        data.dwStateAction = _WTD_STATEACTION_CLOSE
        library.WinVerifyTrust(
            None, ctypes.byref(_ACTION_GUID), ctypes.cast(ctypes.byref(data), ctypes.c_void_p)
        )
    except OSError:
        return None

    code = status & 0xFFFFFFFF
    if code == 0:
        return True
    if code in _NO_SIGNATURE_CODES:
        return False
    return None


__all__ = ["verify_authenticode"]
