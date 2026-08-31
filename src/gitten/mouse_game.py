"""Pure logic for the v1.7 mouse-chase minigame's spawn timing. No Qt --
same "inject the nondeterministic input" discipline `oneliners.py` uses for
its own random interval/RNG, applied here to a second, independent
occasional-event timer.
"""

from __future__ import annotations

import math
import random

DEFAULT_MIN_SPAWN_INTERVAL_MINUTES = 45
DEFAULT_MAX_SPAWN_INTERVAL_MINUTES = 90

DEFAULT_MIN_SPAWN_DISTANCE = 150.0
DEFAULT_SPAWN_MAX_ATTEMPTS = 20


def random_spawn_interval_seconds(
    rng: random.Random | None = None,
    min_minutes: float = DEFAULT_MIN_SPAWN_INTERVAL_MINUTES,
    max_minutes: float = DEFAULT_MAX_SPAWN_INTERVAL_MINUTES,
) -> float:
    """A random interval (in seconds) until the next mouse spawn, uniformly
    between ``min_minutes`` and ``max_minutes``. Pass a seeded ``rng`` in
    tests for determinism; production callers can omit it."""
    r = rng if rng is not None else random
    return r.uniform(min_minutes * 60.0, max_minutes * 60.0)


def should_spawn_mouse(
    view_mode: str,
    is_sulking: bool,
    is_chasing: bool,
    is_dragging: bool,
    is_away: bool = False,
) -> bool:
    """Whether now is a good moment to spawn the mouse: the cat must be in
    its normal "pet" view -- not sulking, not already showing the
    notification inbox, not already mid-chase, not while the user is
    actively dragging the cat around, and (v1.8) not while the user is away
    from the keyboard/mouse -- spawning a minigame nobody is there to play
    is pointless. If not, the caller should skip this occurrence and
    reschedule rather than interrupting or double-spawning."""
    return (
        view_mode == "pet"
        and not is_sulking
        and not is_chasing
        and not is_dragging
        and not is_away
    )


def pick_spawn_position(
    screen_left: float,
    screen_top: float,
    screen_right: float,
    screen_bottom: float,
    cat_x: float,
    cat_y: float,
    rng: random.Random | None = None,
    min_distance: float = DEFAULT_MIN_SPAWN_DISTANCE,
    max_attempts: int = DEFAULT_SPAWN_MAX_ATTEMPTS,
) -> tuple[float, float]:
    """A random point within the given screen rect, far enough from the
    cat's current position to be worth chasing. Retries up to
    ``max_attempts`` times to find a point at least ``min_distance`` away;
    if the rect is too small to ever satisfy that (e.g. a tiny screen), it
    gives up and returns the last sampled point anyway rather than looping
    forever -- still a valid point inside the rect, just not guaranteed to
    meet the minimum distance in that unlikely case."""
    r = rng if rng is not None else random
    x, y = cat_x, cat_y
    for _ in range(max_attempts):
        x = r.uniform(screen_left, screen_right)
        y = r.uniform(screen_top, screen_bottom)
        if math.hypot(x - cat_x, y - cat_y) >= min_distance:
            break
    return (x, y)
