"""Pure logic for the random cute-one-liner nudge. No Qt -- easy to unit
test, following the same "inject the nondeterministic input" discipline
``mood.py`` uses for the clock, applied here to the RNG instead.

This reuses `window.py`'s existing nudge bubble (`show_nudge` / the opacity
fade timeline already built for the distraction nudge) for the actual
display, so this module is only the two small pieces that are genuinely new:
picking a random interval/line, and deciding whether now is a good moment to
interrupt.
"""

from __future__ import annotations

import random

ONELINERS = [
    "یادت نره وقفه بگیری 🙂",
    "کدت امروز قشنگه",
    "یه فنجون چای چطوره؟",
    "commit کوچیک، خوشحالی بزرگ",
    "یه نفس عمیق بکش",
    "داری خیلی خوب پیش میری",
    "چشمات رو یه لحظه ببند و استراحت بده",
    "امروز هم کدنویسی کردی، افرین به تو",
    "یادت باشه آب بخوری",
    "هر خط کد یه قدم به جلوعه",
]

DEFAULT_MIN_INTERVAL_MINUTES = 45
DEFAULT_MAX_INTERVAL_MINUTES = 90


def random_interval_seconds(
    rng: random.Random | None = None,
    min_minutes: float = DEFAULT_MIN_INTERVAL_MINUTES,
    max_minutes: float = DEFAULT_MAX_INTERVAL_MINUTES,
) -> float:
    """A random interval (in seconds) until the next one-liner, uniformly
    between ``min_minutes`` and ``max_minutes``. Pass a seeded ``rng`` in
    tests for determinism; production callers can omit it."""
    r = rng if rng is not None else random
    return r.uniform(min_minutes * 60.0, max_minutes * 60.0)


def pick_oneliner(rng: random.Random | None = None) -> str:
    """A random line from the starter list. Pass a seeded ``rng`` in tests
    for determinism; production callers can omit it."""
    r = rng if rng is not None else random
    return r.choice(ONELINERS)


def should_show_oneliner(
    view_mode: str, is_sulking: bool, is_nudging: bool, is_away: bool = False
) -> bool:
    """Whether now is a good moment to show a one-liner (or, per the same
    gate, the rare shooting-star roll instead): the cat must be in its
    normal idle "pet" view -- not sulking, not already showing another
    nudge, not in the notification inbox view, and (v1.8) not while the
    user is away from the keyboard/mouse -- a cute line nobody is there to
    read is pointless. If not, the caller should skip this occurrence and
    reschedule rather than interrupting."""
    return view_mode == "pet" and not is_sulking and not is_nudging and not is_away


DEFAULT_RARE_EVENT_PROBABILITY = 0.05


def should_show_rare_event(
    rng: random.Random | None = None, probability: float = DEFAULT_RARE_EVENT_PROBABILITY
) -> bool:
    """A small chance (default 5%) that, whenever a one-liner would
    otherwise be shown, a rare "shooting star" event plays instead. Pass a
    seeded ``rng`` in tests for determinism; production callers can omit
    it."""
    r = rng if rng is not None else random
    return r.random() < probability
