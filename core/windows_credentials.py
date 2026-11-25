"""Store application secrets as Windows Credential Manager generic credentials."""

import ctypes
import hashlib
import os
from ctypes import wintypes


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_GENERIC = 1
_LOCAL_MACHINE = 2  # Persistent for the current Windows user on this computer.
_NOT_FOUND = 1168
_MAX_BLOB_SIZE = 2560

if os.name == "nt":
    _advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    _advapi.CredReadW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    )
    _advapi.CredReadW.restype = wintypes.BOOL
    _advapi.CredWriteW.argtypes = (ctypes.POINTER(_Credential), wintypes.DWORD)
    _advapi.CredWriteW.restype = wintypes.BOOL
    _advapi.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    _advapi.CredDeleteW.restype = wintypes.BOOL
    _advapi.CredFree.argtypes = (ctypes.c_void_p,)
    _advapi.CredFree.restype = None


def _target(db_path, key):
    if os.name != "nt":
        raise OSError("Ứng dụng cần Windows Credential Manager để lưu thông tin đăng nhập.")
    location = os.path.normcase(os.path.realpath(db_path))
    instance = hashlib.sha256(os.fsencode(location)).hexdigest()
    return f"TroLyCongVan_DRVN/{instance}/{key}"


def read(db_path, key, default=""):
    target = _target(db_path, key)
    result = ctypes.POINTER(_Credential)()
    if not _advapi.CredReadW(target, _GENERIC, 0, ctypes.byref(result)):
        error = ctypes.get_last_error()
        if error == _NOT_FOUND:
            return default
        raise ctypes.WinError(error)
    try:
        entry = result.contents
        return ctypes.string_at(entry.CredentialBlob, entry.CredentialBlobSize).decode("utf-8")
    finally:
        _advapi.CredFree(result)


def write(db_path, key, value):
    target = _target(db_path, key)
    if not value:
        if not _advapi.CredDeleteW(target, _GENERIC, 0):
            error = ctypes.get_last_error()
            if error != _NOT_FOUND:
                raise ctypes.WinError(error)
        return

    encoded = value.encode("utf-8")
    if len(encoded) > _MAX_BLOB_SIZE:
        raise ValueError("Thông tin đăng nhập vượt giới hạn của Windows Credential Manager.")
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    entry = _Credential(
        Type=_GENERIC,
        TargetName=target,
        CredentialBlobSize=len(encoded),
        CredentialBlob=blob,
        Persist=_LOCAL_MACHINE,
    )
    if not _advapi.CredWriteW(ctypes.byref(entry), 0):
        raise ctypes.WinError(ctypes.get_last_error())
