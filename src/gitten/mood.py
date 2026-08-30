"""Pure mood state machine for Gitten. No Qt imports -- easy to unit test.

The machine is driven by two kinds of input, both timestamped by the caller
(so tests can inject fake clocks instead of sleeping):

- ``on_commit(now)``      -- a commit was just observed in the watched repo.
- ``update_dirty(is_dirty, now)`` -- the result of a ``git status --porcelain``
  check: whether the working tree currently has uncommitted changes.

And one time-based input:

- ``tick(now)`` -- called periodically so the machine can expire the
  transient "happy" celebration and notice that uncommitted changes have
  been sitting around long enough to become "waiting".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Mood(Enum):
    IDLE = "idle"
    HAPPY = "happy"
    WAITING = "waiting"


DEFAULT_HAPPY_SECONDS = 4.0
DEFAULT_WAITING_THRESHOLD_SECONDS = 30 * 60.0


@dataclass
class MoodMachine:
    """Tracks the kitten's mood over time from git signals.

    ``now`` is always a float, typically ``time.monotonic()`` in production
    and an arbitrary increasing counter in tests.
    """

    happy_seconds: float = DEFAULT_HAPPY_SECONDS
    waiting_threshold_seconds: float = DEFAULT_WAITING_THRESHOLD_SECONDS

    mood: Mood = Mood.IDLE
    is_dirty: bool = False
    dirty_since: float | None = None
    happy_until: float | None = None

    def on_commit(self, now: float) -> Mood:
        """A commit was observed: celebrate, and clear any dirty streak."""
        self.is_dirty = False
        self.dirty_since = None
        self.happy_until = now + self.happy_seconds
        self.mood = Mood.HAPPY
        return self.mood

    def update_dirty(self, is_dirty: bool, now: float) -> Mood:
        """Feed in the latest ``git status`` result."""
        if is_dirty and not self.is_dirty:
            self.dirty_since = now
        elif not is_dirty:
            self.dirty_since = None
        self.is_dirty = is_dirty
        return self.tick(now)

    def tick(self, now: float) -> Mood:
        """Re-evaluate mood given the current time. Call this periodically."""
        if self.happy_until is not None and now < self.happy_until:
            return self.mood

        self.happy_until = None

        if (
            self.is_dirty
            and self.dirty_since is not None
            and now - self.dirty_since >= self.waiting_threshold_seconds
        ):
            self.mood = Mood.WAITING
        else:
            self.mood = Mood.IDLE

        return self.mood
