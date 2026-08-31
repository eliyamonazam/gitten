import random

from gitten.oneliners import (
    ONELINERS,
    pick_oneliner,
    random_interval_seconds,
    should_show_oneliner,
    should_show_rare_event,
)


# -- random_interval_seconds --------------------------------------------------


def test_interval_within_default_bounds_across_many_seeds():
    rng = random.Random(0)
    for _ in range(500):
        seconds = random_interval_seconds(rng)
        assert 45 * 60.0 <= seconds <= 90 * 60.0


def test_interval_respects_custom_bounds():
    rng = random.Random(1)
    for _ in range(200):
        seconds = random_interval_seconds(rng, min_minutes=10, max_minutes=20)
        assert 10 * 60.0 <= seconds <= 20 * 60.0


def test_interval_is_deterministic_given_a_seeded_rng():
    a = random_interval_seconds(random.Random(42))
    b = random_interval_seconds(random.Random(42))
    assert a == b


# -- pick_oneliner -------------------------------------------------------------


def test_pick_oneliner_returns_one_of_the_starter_list():
    rng = random.Random(2)
    for _ in range(50):
        assert pick_oneliner(rng) in ONELINERS


def test_starter_list_has_several_lines():
    assert len(ONELINERS) >= 8


# -- should_show_oneliner -------------------------------------------------------


def test_shows_when_idle_pet_view_and_nothing_else_going_on():
    assert should_show_oneliner("pet", is_sulking=False, is_nudging=False) is True


def test_skips_when_sulking():
    assert should_show_oneliner("pet", is_sulking=True, is_nudging=False) is False


def test_skips_when_already_nudging():
    assert should_show_oneliner("pet", is_sulking=False, is_nudging=True) is False


def test_skips_when_in_inbox_view():
    assert should_show_oneliner("inbox", is_sulking=False, is_nudging=False) is False


def test_skips_when_away():
    assert (
        should_show_oneliner("pet", is_sulking=False, is_nudging=False, is_away=True) is False
    )


def test_skips_when_everything_is_going_on_at_once():
    assert (
        should_show_oneliner("inbox", is_sulking=True, is_nudging=True, is_away=True) is False
    )


# -- should_show_rare_event -----------------------------------------------------


def test_rare_event_fraction_is_close_to_probability_over_many_draws():
    rng = random.Random(7)
    trials = 20000
    hits = sum(1 for _ in range(trials) if should_show_rare_event(rng))
    fraction = hits / trials
    # default probability is 0.05 -- allow a generous tolerance band since
    # this is a statistical check, not an exact one.
    assert 0.03 <= fraction <= 0.07


def test_rare_event_respects_custom_probability():
    rng = random.Random(11)
    trials = 5000
    hits = sum(1 for _ in range(trials) if should_show_rare_event(rng, probability=0.5))
    fraction = hits / trials
    assert 0.45 <= fraction <= 0.55


def test_rare_event_probability_zero_never_fires():
    rng = random.Random(3)
    assert all(not should_show_rare_event(rng, probability=0.0) for _ in range(1000))


def test_rare_event_probability_one_always_fires():
    rng = random.Random(5)
    assert all(should_show_rare_event(rng, probability=1.0) for _ in range(1000))


def test_rare_event_is_deterministic_given_a_seeded_rng():
    a = should_show_rare_event(random.Random(99))
    b = should_show_rare_event(random.Random(99))
    assert a == b
