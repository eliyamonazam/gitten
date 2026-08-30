import random

from gitten.oneliners import (
    ONELINERS,
    pick_oneliner,
    random_interval_seconds,
    should_show_oneliner,
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


def test_skips_when_everything_is_going_on_at_once():
    assert should_show_oneliner("inbox", is_sulking=True, is_nudging=True) is False
