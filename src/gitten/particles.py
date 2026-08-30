"""A small, generic, reusable fading-particle system. No Qt -- same
pure/Qt split already used everywhere else (e.g. `mood.py` vs. `sprite.py`):
this module only tracks particle state (spawn, age, prune, drift), fully
testable with fake timestamps; the actual drawing lives in `sprite.py`'s
`draw_particles`, which takes plain `(x, y, opacity)` tuples and knows
nothing about time or lifespans.

Deliberately generic -- not hardcoded to "drag trail" -- so Feature 3's
shooting star can reuse the exact same system for a different visual
(a single particle launched across the window) just by spawning it with a
longer lifespan and a drift vector instead of the drag trail's short-lived,
stationary sparkles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_LIFESPAN_SECONDS = 0.7


@dataclass
class Particle:
    x: float
    y: float
    spawned_at: float
    lifespan: float = DEFAULT_LIFESPAN_SECONDS
    dx: float = 0.0
    dy: float = 0.0


@dataclass
class ParticleSystem:
    particles: list[Particle] = field(default_factory=list)

    def spawn_particle(
        self,
        x: float,
        y: float,
        now: float,
        lifespan: float = DEFAULT_LIFESPAN_SECONDS,
        dx: float = 0.0,
        dy: float = 0.0,
    ) -> None:
        self.particles.append(Particle(x=x, y=y, spawned_at=now, lifespan=lifespan, dx=dx, dy=dy))

    def update_and_prune(self, now: float) -> None:
        """Drop any particle older than its own lifespan. Call this once per
        frame before rendering."""
        self.particles = [p for p in self.particles if now - p.spawned_at < p.lifespan]

    def positions(self, now: float) -> list[tuple[float, float, float]]:
        """(x, y, opacity) for each currently-alive particle: position
        advanced by its drift vector, opacity fading linearly from 1.0 (just
        spawned) to 0.0 (about to expire). Call `update_and_prune` first so
        this only reflects particles that are actually still alive."""
        result = []
        for p in self.particles:
            age = max(0.0, now - p.spawned_at)
            opacity = max(0.0, 1.0 - age / p.lifespan)
            result.append((p.x + p.dx * age, p.y + p.dy * age, opacity))
        return result
