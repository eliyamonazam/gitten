"""Pure logic for the daily commit streak. No Qt, no subprocess -- easy to
unit test with fake date lists, following the same discipline as ``mood.py``.

The streak is always recomputed from scratch from the full list of distinct
commit days rather than kept as a running counter, so it can never drift out
of sync with the actual git history (the same idiom already used by
``git_watcher.count_commits_today``).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


def compute_streak(commit_dates: Iterable[str], today: date) -> int:
    """Given commit dates as ``YYYY-MM-DD`` strings (as produced by
    ``git log --date=short``) and the current date, return the length of the
    current consecutive-day streak.

    Counts backward from today if today already has a commit, or from
    yesterday if today doesn't have one yet (so the streak isn't considered
    broken just because it's still early in the day) -- one gap breaks it.
    """
    days = {date.fromisoformat(d) for d in commit_dates}

    if today in days:
        cursor = today
    elif today - timedelta(days=1) in days:
        cursor = today - timedelta(days=1)
    else:
        return 0

    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
