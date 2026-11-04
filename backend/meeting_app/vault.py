"""Windows DPAPI: secrets are encrypted for the current Windows user."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from threading import RLock


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('此版本使用 Windows DPAPI 保存凭据，请在 Windows 上运行。')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), 'MeetingStudio', None, None, None, 1, ctypes.byref(result))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


class Vault:
    def __init__(self, directory: Path):
        self.path = directory / 'credentials.dpapi.json'
        self.lock = RLock()

    def _read(self):
        return json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}

    def get(self, name: str) -> str:
        with self.lock:
            raw = self._read().get(name)
        return protect(base64.b64decode(raw), True).decode('utf-8') if raw else ''

    def set(self, name: str, value: str):
        with self.lock:
            payload = self._read()
            if value:
                payload[name] = base64.b64encode(protect(value.encode('utf-8'))).decode('ascii')
            else:
                payload.pop(name, None)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(payload), 'utf-8')
            temporary.replace(self.path)

    def configured(self, name: str) -> bool:
        return bool(self._read().get(name))
