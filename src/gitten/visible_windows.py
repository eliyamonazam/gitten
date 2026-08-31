"""Enumerates visible, titled top-level windows and resolves each to its
owning process ID (Windows-only), used by the v1.6 "curiosity" reaction.
The actual "is this a new launch" decision lives in `app_launch.py` as
pure, testable logic -- this module is only the win32 I/O boundary, same
thin-wrapper split already used for `foreground_window.py`.
"""

from __future__ import annotations

import os

try:
    import win32gui
    import win32process
except ImportError:  # pragma: no cover - non-Windows fallback
    win32gui = None
    win32process = None


def get_visible_window_pids() -> set[int]:
    """Return the set of distinct PIDs that own at least one visible,
    non-empty-titled top-level window -- the practical definition of "the
    user opened a program", as opposed to one of the many invisible
    background/helper processes Windows is always spawning. Gitten's own
    process is excluded so it never reacts to itself. Returns an empty set
    if win32 isn't available (non-Windows)."""
    if win32gui is None:
        return set()

    own_pid = os.getpid()
    pids: set[int] = set()

    def _visit(hwnd, _extra) -> bool:
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if pid and pid != own_pid:
                pids.add(pid)
        return True

    win32gui.EnumWindows(_visit, None)
    return pids
