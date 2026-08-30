"""Pure logic for the social-media / distraction nudge. No Qt, no win32 --
easy to unit test, following the same pattern as ``mood.py``.

Three independent pieces live here:

- ``is_distracting_window`` -- given a foreground process name + title,
  decide whether it matches the (user-editable) distraction list.
- ``DistractionTracker`` -- tracks a continuous "distracted" streak over
  time (fed by timestamps from the caller, same as ``MoodMachine``) and
  decides when a nudge should fire.
- ``load_distraction_lists`` / ``DEFAULT_*`` -- the default title/process
  lists and a small JSON-file loader so a user can edit them without a
  full settings UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DISTRACTING_TITLES = [
    "instagram",
    "twitter",
    "x.com",
    "tiktok",
    "reddit",
    "youtube",
]
DEFAULT_DISTRACTING_PROCESSES = [
    "telegram.exe",
    "discord.exe",
]

DEFAULT_THRESHOLD_SECONDS = 20 * 60.0
DEFAULT_CONFIG_PATH = Path.home() / ".gitten" / "distraction_config.json"


def is_distracting_window(
    process_name: str,
    title: str,
    distracting_titles: list[str] | None = None,
    distracting_processes: list[str] | None = None,
) -> bool:
    """Case-insensitive substring match on title, exact match on process name."""
    titles = distracting_titles if distracting_titles is not None else DEFAULT_DISTRACTING_TITLES
    processes = (
        distracting_processes
        if distracting_processes is not None
        else DEFAULT_DISTRACTING_PROCESSES
    )

    if process_name and process_name.strip().lower() in {p.lower() for p in processes}:
        return True

    title_lower = title.lower()
    return any(t.lower() in title_lower for t in titles if t)


def load_distraction_lists(
    path: Path = DEFAULT_CONFIG_PATH,
) -> tuple[list[str], list[str]]:
    """Load user-editable title/process lists from a JSON file, e.g.::

        {"titles": ["instagram", ...], "processes": ["telegram.exe", ...]}

    Falls back to the shipped defaults if the file is missing or invalid.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        titles = [str(t) for t in data.get("titles", DEFAULT_DISTRACTING_TITLES)]
        processes = [str(p) for p in data.get("processes", DEFAULT_DISTRACTING_PROCESSES)]
        return titles, processes
    except (OSError, ValueError, AttributeError):
        return list(DEFAULT_DISTRACTING_TITLES), list(DEFAULT_DISTRACTING_PROCESSES)


@dataclass
class DistractionTracker:
    """Tracks a continuous streak of "distracted" time and decides when to
    fire a gentle nudge.

    A nudge fires once the streak crosses ``threshold_seconds``, and then
    again every additional ``threshold_seconds`` while the streak keeps
    going uninterrupted -- so a long binge gets nudged roughly every
    threshold period, not just once ever. The instant the foreground
    window stops matching, the streak (and the nudge cadence) resets.
    """

    threshold_seconds: float = DEFAULT_THRESHOLD_SECONDS
    streak_start: float | None = None
    _next_fire_elapsed: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._next_fire_elapsed = self.threshold_seconds

    def update(self, is_distracting: bool, now: float) -> bool:
        """Feed in the latest foreground-window match result.

        Returns True the instant a nudge should fire.
        """
        if not is_distracting:
            self.streak_start = None
            self._next_fire_elapsed = self.threshold_seconds
            return False

        if self.streak_start is None:
            self.streak_start = now
            self._next_fire_elapsed = self.threshold_seconds

        elapsed = now - self.streak_start
        if elapsed >= self._next_fire_elapsed:
            self._next_fire_elapsed += self.threshold_seconds
            return True
        return False
