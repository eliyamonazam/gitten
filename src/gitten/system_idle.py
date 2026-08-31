"""Real system-wide keyboard/mouse idle detection (v1.8), via the standard
Windows `GetLastInputInfo` API through `ctypes` -- same "thin I/O boundary,
no decision logic" spirit as `system_monitor.py` / `foreground_window.py`:
this file is the only thing that touches ctypes/user32 for idle detection.

The one pure decision this feature needs (`is_away`) lives right alongside
the I/O wrapper rather than in a separate module the way `app_launch.py` is
split from `visible_windows.py` -- that split exists because that pure
module grew real branching logic worth isolating and unit-testing on its
own; `is_away` is a single threshold comparison, so keeping it in the same
small file is simpler without losing any testability (it still doesn't
import ctypes or touch Windows at all).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

DEFAULT_AWAY_THRESHOLD_SECONDS = 600.0  # 10 minutes


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_idle_seconds() -> float:
    """Seconds since the last system-wide keyboard/mouse input.

    Uses `GetTickCount64` (not `GetTickCount`) to compute elapsed time so
    this doesn't silently misbehave once the machine has been up for more
    than ~49.7 days, the point at which the 32-bit tick counter wraps
    around. Returns 0.0 (treated as "not idle") on any failure -- a missing
    `user32`/non-Windows platform, or the call itself failing -- rather than
    raising, the same "degrade gracefully" discipline every other
    win32-touching module in this codebase already follows.
    """
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        millis_since_boot = ctypes.windll.kernel32.GetTickCount64()
        idle_millis = millis_since_boot - info.dwTime
        return max(0.0, idle_millis / 1000.0)
    except (AttributeError, OSError, ValueError):
        return 0.0


def is_away(
    idle_seconds: float, threshold_seconds: float = DEFAULT_AWAY_THRESHOLD_SECONDS
) -> bool:
    """Whether the user counts as "away" from the keyboard/mouse right now.

    Deliberately a simple binary gate rather than graduated idle levels --
    this codebase's other binary state gates (sulking, focus) have worked
    fine as plain booleans, and there's no established need here for
    anything more granular than "away" / "not away".
    """
    return idle_seconds >= threshold_seconds
