"""Small, per-Windows-user protected records. No plaintext fallback."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile

KINDS = ("bank", "docusign", "sam")


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, encrypt):
    if os.name != "nt":
        raise OSError("Protected accounts require Windows.")
    if not 0 < len(data) <= 65536:
        raise ValueError("Invalid protected record size.")
    crypt = ctypes.WinDLL("crypt32.dll", winmode=0x800)
    kernel = ctypes.WinDLL("kernel32.dll", winmode=0x800)
    ptr = ctypes.POINTER(_Blob)
    function = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    function.argtypes = [ptr, ctypes.c_void_p, ptr, ctypes.c_void_p, ctypes.c_void_p,
                         wintypes.DWORD, ptr]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    raw = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, output = _Blob(len(data), raw), _Blob()
    try:
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise OSError("Windows could not protect or unlock this account.")
        try:
            return ctypes.string_at(output.data, output.size)
        finally:
            ctypes.memset(output.data, 0, output.size)
            kernel.LocalFree(output.data)
    finally:
        ctypes.memset(raw, 0, len(raw))


class AccountVault:
    def __init__(self, directory):
        self.directory = Path(directory)

    def path(self, kind):
        if kind not in KINDS:
            raise ValueError("Unknown account type.")
        return self.directory / ("account-" + kind + ".dpapi")

    def load(self, kind):
        path = self.path(kind)
        try:
            with path.open("rb") as handle:
                data = handle.read(65537)
        except FileNotFoundError:
            return None
        record = json.loads(_crypt(data, False))
        if record.get("kind") != kind or type(record.get("value")) is not dict:
            raise ValueError("Account record mismatch.")
        return record["value"]

    def save(self, kind, value):
        path = self.path(kind)
        payload = json.dumps(dict(kind=kind, value=value), allow_nan=False).encode()
        encrypted = _crypt(payload, True)
        with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as handle:
            temp = Path(handle.name)
            try:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            except BaseException:
                handle.close()
                temp.unlink(missing_ok=True)
                raise
        try:
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def forget(self, kind):
        self.path(kind).unlink(missing_ok=True)
