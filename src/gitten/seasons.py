"""Two small, independent pure functions for seasonal/time-of-day flavor.
No Qt, no subprocess -- easy to unit test, same discipline as `streak.py`.
"""

from __future__ import annotations

from datetime import date

_HALLOWEEN = (10, 31)
_YALDA = (12, 21)  # approximate -- the actual solstice date drifts by a day


def seasonal_accessory(today: date, birthday: date | None = None) -> str | None:
    """Which seasonal accessory (if any) the cat should wear today:
    ``"halloween"`` (Oct 31), ``"yalda"`` (~Dec 21), ``"birthday"`` (if
    ``birthday``'s month/day -- its year is ignored -- matches today), or
    ``None``. Fixed calendar occasions are checked before the birthday, so
    a birthday that happens to fall on Halloween or Yalda shows that
    occasion's accessory instead."""
    if (today.month, today.day) == _HALLOWEEN:
        return "halloween"
    if (today.month, today.day) == _YALDA:
        return "yalda"
    if birthday is not None and (today.month, today.day) == (birthday.month, birthday.day):
        return "birthday"
    return None


_NIGHT_START_HOUR = 23
_NIGHT_END_HOUR = 7


def is_night_time(hour: int) -> bool:
    """Whether `hour` (24-hour, 0-23) falls in the night window, 23:00-7:00."""
    return hour >= _NIGHT_START_HOUR or hour < _NIGHT_END_HOUR
