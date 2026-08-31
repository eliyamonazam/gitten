"""System-wide global hotkey (v1.9 Part 4) that summons the command bar
from anywhere, even when Gitten isn't the focused app -- registered via the
standard Windows `RegisterHotKey` API through `ctypes`, consistent with
this codebase's existing raw-win32-API style (`system_idle.py`,
`foreground_window.py`) rather than pulling in a third-party hotkey
library.

`RegisterHotKey` binds the combination to a specific window handle's
message queue; the actual `WM_HOTKEY` message is then intercepted here via
a `QAbstractNativeEventFilter`, which Qt calls for every native message it
pumps through the app's own event loop on that same thread -- no second
message loop or polling needed.

TODO: Ctrl+Alt+G is hardcoded below since there's no settings UI yet to let
the user pick their own combination -- make this configurable once one
exists.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
VK_G = 0x47
WM_HOTKEY = 0x0312
DEFAULT_HOTKEY_ID = 1


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    """Watches every native Windows message Qt's event loop pumps through
    and calls `callback` the instant the registered hotkey's WM_HOTKEY
    arrives. The caller must keep a Python reference to this object for as
    long as the hotkey should stay active -- `installNativeEventFilter`
    does not itself keep the filter alive."""

    def __init__(self, hotkey_id: int, callback) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                self._callback()
        return False, 0


def register_global_hotkey(
    hwnd: int, callback, hotkey_id: int = DEFAULT_HOTKEY_ID
) -> _HotkeyEventFilter | None:
    """Registers Ctrl+Alt+G as a system-wide hotkey bound to `hwnd`'s
    message queue, and returns the native-event filter that will call
    `callback` when it fires (the caller must
    `app.installNativeEventFilter(...)` it and keep the reference alive).

    Returns None -- logging why, never raising or crashing -- if
    registration fails, e.g. another app already owns that combination.
    This is the same "check the return value, degrade gracefully" discipline
    every other win32-touching module in this codebase already follows.
    """
    ok = ctypes.windll.user32.RegisterHotKey(
        wintypes.HWND(int(hwnd)), hotkey_id, MOD_CONTROL | MOD_ALT, VK_G
    )
    if not ok:
        error_code = ctypes.GetLastError()
        print(
            f"gitten: RegisterHotKey(Ctrl+Alt+G) failed (error {error_code}) -- "
            "another app may already be using this combination. The command "
            "bar can still be summoned normally; the global hotkey just "
            "won't work this session."
        )
        return None
    return _HotkeyEventFilter(hotkey_id, callback)


def unregister_global_hotkey(hwnd: int, hotkey_id: int = DEFAULT_HOTKEY_ID) -> None:
    ctypes.windll.user32.UnregisterHotKey(wintypes.HWND(int(hwnd)), hotkey_id)
