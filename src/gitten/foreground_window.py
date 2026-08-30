"""Reads the foreground window's process name and title (Windows-only), used
by the social/distraction nudge feature. The actual "is this distracting"
decision lives in ``distraction.py`` as pure, testable logic -- this module
is only the win32 I/O boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil

try:
    import win32gui
    import win32process
except ImportError:  # pragma: no cover - non-Windows fallback
    win32gui = None
    win32process = None


@dataclass
class ForegroundWindow:
    process_name: str
    title: str


def get_foreground_window() -> ForegroundWindow | None:
    """Return the current foreground window's process name + title, or
    None if it can't be determined (no window, non-Windows, access denied)."""
    if win32gui is None:
        return None

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None

    title = win32gui.GetWindowText(hwnd) or ""
    process_name = ""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process_name = psutil.Process(pid).name()
    except (psutil.Error, OSError):
        pass

    return ForegroundWindow(process_name=process_name, title=title)
