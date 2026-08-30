"""Sulking & reconciliation -- a third independent state layer.

Same discipline as `mood.py` / `status_badge.py` / `distraction.py`: no Qt
imports, every timestamp passed in by the caller rather than read from the
system clock, so it's fully unit-testable without a running app. This is
deliberately independent from `mood.py` and `status_badge.py` -- the cat can
be sulking while also showing a "happy" git mood or a low-battery badge, the
same way v1.1 kept mood and status badges independent of each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

SULK_THRESHOLD_SECONDS = 30 * 60.0
PETS_TO_RECONCILE = 4


class AttentionState(Enum):
    NORMAL = auto()
    SULKING = auto()


def turn_stage(pets_received: int) -> int:
    """0 = fully turned away .. 4 = fully reconciled (front-facing)."""
    return max(0, min(PETS_TO_RECONCILE, pets_received))


@dataclass
class AttentionTracker:
    last_interaction_at: float | None = None
    state: AttentionState = AttentionState.NORMAL
    pets_received: int = field(default=0)

    def register_interaction(self, now: float) -> None:
        """Any click or drag on the cat, in any state, resets the sulk clock."""
        self.last_interaction_at = now

    def register_pet(self, now: float) -> None:
        """A plain click-in-place while SULKING -- one step of reconciliation.

        Also counts as an interaction (resets the sulk clock), same as any
        other click.
        """
        self.register_interaction(now)
        if self.state != AttentionState.SULKING:
            return
        self.pets_received += 1
        if turn_stage(self.pets_received) >= PETS_TO_RECONCILE:
            self.state = AttentionState.NORMAL
            self.pets_received = 0

    def tick(self, now: float) -> AttentionState:
        """Periodic re-evaluation: start sulking once neglected long enough."""
        if self.last_interaction_at is None:
            self.last_interaction_at = now
        if (
            self.state == AttentionState.NORMAL
            and now - self.last_interaction_at >= SULK_THRESHOLD_SECONDS
        ):
            self.state = AttentionState.SULKING
            self.pets_received = 0
        return self.state
