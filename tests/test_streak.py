from datetime import date

from gitten.streak import commits_by_day, compute_streak, longest_streak


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


# -- commits_by_day -----------------------------------------------------


def test_commits_by_day_empty_history_is_all_zero():
    counts = commits_by_day([], weeks=2, today=d("2026-08-31"))
    assert len(counts) == 14
    assert set(counts.values()) == {0}


def test_commits_by_day_window_size_and_bounds():
    counts = commits_by_day([], weeks=3, today=d("2026-08-31"))
    assert len(counts) == 21
    assert min(counts) == d("2026-08-11")
    assert max(counts) == d("2026-08-31")


def test_commits_by_day_history_spanning_fewer_than_requested_weeks():
    dates = ["2026-08-30", "2026-08-31"]
    counts = commits_by_day(dates, weeks=12, today=d("2026-08-31"))
    assert len(counts) == 84
    assert counts[d("2026-08-30")] == 1
    assert counts[d("2026-08-31")] == 1
    assert sum(counts.values()) == 2


def test_commits_by_day_counts_multiple_commits_same_day():
    dates = ["2026-08-31", "2026-08-31", "2026-08-31"]
    counts = commits_by_day(dates, weeks=1, today=d("2026-08-31"))
    assert counts[d("2026-08-31")] == 3


def test_commits_by_day_ignores_dates_outside_the_window():
    dates = ["2020-01-01"]
    counts = commits_by_day(dates, weeks=1, today=d("2026-08-31"))
    assert sum(counts.values()) == 0


# -- longest_streak -------------------------------------------------------


def test_longest_streak_empty_history():
    assert longest_streak([]) == 0


def test_longest_streak_no_gaps():
    dates = ["2026-08-29", "2026-08-30", "2026-08-31"]
    assert longest_streak(dates) == 3


def test_longest_streak_with_one_gap_picks_the_longer_run():
    dates = ["2026-08-01", "2026-08-02", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13"]
    assert longest_streak(dates) == 4


def test_longest_streak_best_run_is_in_the_past_not_the_current_run():
    # A 5-day run well in the past, and a shorter 2-day run right at the
    # end -- an implementation that only ever looks at the most recent run
    # would wrongly return 2 here instead of 5.
    dates = [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
        "2026-06-05",
        "2026-08-30",
        "2026-08-31",
    ]
    assert longest_streak(dates) == 5


def test_longest_streak_duplicate_dates_dont_inflate_it():
    dates = ["2026-08-31", "2026-08-31", "2026-08-30"]
    assert longest_streak(dates) == 2
