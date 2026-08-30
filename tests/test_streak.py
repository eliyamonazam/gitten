from datetime import date

from gitten.streak import compute_streak


def d(s):
    return date.fromisoformat(s)


def test_empty_list_has_no_streak():
    assert compute_streak([], today=d("2026-08-31")) == 0


def test_single_commit_today_is_streak_of_one():
    assert compute_streak(["2026-08-31"], today=d("2026-08-31")) == 1


def test_single_commit_yesterday_and_nothing_today_still_counts():
    assert compute_streak(["2026-08-30"], today=d("2026-08-31")) == 1


def test_no_commit_today_or_yesterday_is_broken():
    assert compute_streak(["2026-08-25"], today=d("2026-08-31")) == 0


def test_contiguous_streak_including_today():
    dates = ["2026-08-29", "2026-08-30", "2026-08-31"]
    assert compute_streak(dates, today=d("2026-08-31")) == 3


def test_contiguous_streak_ending_yesterday():
    dates = ["2026-08-28", "2026-08-29", "2026-08-30"]
    assert compute_streak(dates, today=d("2026-08-31")) == 3


def test_gap_breaks_the_streak():
    dates = ["2026-08-25", "2026-08-29", "2026-08-30", "2026-08-31"]
    assert compute_streak(dates, today=d("2026-08-31")) == 3


def test_duplicate_dates_dont_inflate_streak():
    dates = ["2026-08-31", "2026-08-31", "2026-08-30"]
    assert compute_streak(dates, today=d("2026-08-31")) == 2


def test_accepts_a_set_too():
    dates = {"2026-08-31", "2026-08-30"}
    assert compute_streak(dates, today=d("2026-08-31")) == 2
