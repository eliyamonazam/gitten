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


def commits_by_day(
    commit_dates: Iterable[str], weeks: int = 12, today: date | None = None
) -> dict[date, int]:
    """Per-day commit counts for the last ``weeks`` weeks (today inclusive),
    for the v1.12 dashboard's GitHub-contribution-style heatmap. Built from
    the same ``YYYY-MM-DD`` date strings ``compute_streak`` consumes -- one
    entry per commit, duplicates expected for multiple commits on the same
    day (unlike ``compute_streak``, which only cares about *which* days had
    at least one commit, this genuinely counts them).

    Every day in the window is present in the result, 0 if it had no
    commits, not just days that had activity -- so a caller can render a
    full, gap-free grid without special-casing missing keys. ``today`` is
    injectable (same "pass in the clock" idiom as ``compute_streak``) so
    this is testable with fake dates.
    """
    if today is None:
        today = date.today()
    window_start = today - timedelta(days=weeks * 7 - 1)
    counts: dict[date, int] = {
        window_start + timedelta(days=i): 0 for i in range(weeks * 7)
    }
    for d in commit_dates:
        day = date.fromisoformat(d)
        if day in counts:
            counts[day] += 1
    return counts


def longest_streak(commit_dates: Iterable[str]) -> int:
    """The longest run of consecutive days anywhere in the full commit
    history -- unlike ``compute_streak``, which only ever measures the
    *current* run ending today (or yesterday), this scans the whole history
    for the best run wherever it happened, including entirely in the past.

    O(n): for each day whose previous day has no commit (i.e. every
    possible streak start), count forward from there -- so every day is
    only ever the start of at most one scan, rather than re-walking
    overlapping runs from every day in them.
    """
    days = {date.fromisoformat(d) for d in commit_dates}
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue
        length = 1
        cursor = day + timedelta(days=1)
        while cursor in days:
            length += 1
            cursor += timedelta(days=1)
        best = max(best, length)
    return best
