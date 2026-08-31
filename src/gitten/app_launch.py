"""Pure logic for the "curiosity" reaction (v1.6): react when a genuinely
new program is opened. No Qt, no win32 -- the actual enumeration of visible
top-level windows and their owning PIDs is the win32 I/O boundary and lives
in `visible_windows.py` instead, same "thin I/O boundary" split already
used for `foreground_window.py` vs. `distraction.py`.
"""

from __future__ import annotations

DEFAULT_COOLDOWN_SECONDS = 10.0


def should_react_to_new_launch(
    previous_pids: set[int],
    current_pids: set[int],
    last_reaction_at: float | None,
    now: float,
    cooldown: float = DEFAULT_COOLDOWN_SECONDS,
) -> bool:
    """True if at least one process with a visible, titled window appeared
    since the previous poll, and the cooldown since the last reaction has
    elapsed (or there's never been one yet).

    `previous_pids` empty is treated as "no baseline established yet" (the
    very first poll) rather than "everything currently open just launched
    simultaneously" -- otherwise every already-running program at startup
    would look like N new launches at once. The caller is expected to seed
    `previous_pids` as an empty set before the first poll and simply record
    whatever `current_pids` was afterward, win or lose, so the *next* poll
    has a real baseline to compare against.
    """
    if not previous_pids:
        return False
    if not (current_pids - previous_pids):
        return False
    if last_reaction_at is not None and now - last_reaction_at < cooldown:
        return False
    return True
