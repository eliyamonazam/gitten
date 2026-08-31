import math
import random

from gitten.mouse_game import (
    DEFAULT_MIN_SPAWN_DISTANCE,
    pick_spawn_position,
    random_spawn_interval_seconds,
    should_spawn_mouse,
)


# -- random_spawn_interval_seconds -------------------------------------------


def test_interval_within_default_bounds_across_many_seeds():
    rng = random.Random(0)
    for _ in range(500):
        seconds = random_spawn_interval_seconds(rng)
        assert 45 * 60.0 <= seconds <= 90 * 60.0


def test_interval_respects_custom_bounds():
    rng = random.Random(1)
    for _ in range(200):
        seconds = random_spawn_interval_seconds(rng, min_minutes=5, max_minutes=15)
        assert 5 * 60.0 <= seconds <= 15 * 60.0


def test_interval_is_deterministic_given_a_seeded_rng():
    a = random_spawn_interval_seconds(random.Random(42))
    b = random_spawn_interval_seconds(random.Random(42))
    assert a == b


# -- should_spawn_mouse -------------------------------------------------------


def test_spawns_when_idle_pet_view_and_nothing_else_going_on():
    assert should_spawn_mouse("pet", is_sulking=False, is_chasing=False, is_dragging=False) is True


def test_skips_when_sulking():
    assert should_spawn_mouse("pet", is_sulking=True, is_chasing=False, is_dragging=False) is False


def test_skips_when_in_inbox_view():
    assert should_spawn_mouse("inbox", is_sulking=False, is_chasing=False, is_dragging=False) is False


def test_skips_when_already_chasing():
    assert should_spawn_mouse("pet", is_sulking=False, is_chasing=True, is_dragging=False) is False


def test_skips_when_dragging():
    assert should_spawn_mouse("pet", is_sulking=False, is_chasing=False, is_dragging=True) is False


def test_skips_when_away():
    assert (
        should_spawn_mouse(
            "pet", is_sulking=False, is_chasing=False, is_dragging=False, is_away=True
        )
        is False
    )


def test_skips_when_everything_is_going_on_at_once():
    assert (
        should_spawn_mouse(
            "inbox", is_sulking=True, is_chasing=True, is_dragging=True, is_away=True
        )
        is False
    )


# -- pick_spawn_position -------------------------------------------------------


def test_spawn_position_always_inside_screen_rect():
    rng = random.Random(4)
    for _ in range(500):
        x, y = pick_spawn_position(0, 0, 1920, 1080, cat_x=960, cat_y=540, rng=rng)
        assert 0 <= x <= 1920
        assert 0 <= y <= 1080


def test_spawn_position_satisfies_min_distance_when_screen_is_large_enough():
    rng = random.Random(9)
    for _ in range(500):
        x, y = pick_spawn_position(0, 0, 1920, 1080, cat_x=960, cat_y=540, rng=rng)
        assert math.hypot(x - 960, y - 540) >= DEFAULT_MIN_SPAWN_DISTANCE


def test_spawn_position_respects_custom_min_distance():
    rng = random.Random(13)
    for _ in range(200):
        x, y = pick_spawn_position(
            0, 0, 1920, 1080, cat_x=960, cat_y=540, rng=rng, min_distance=500.0
        )
        assert math.hypot(x - 960, y - 540) >= 500.0


def test_spawn_position_terminates_when_min_distance_is_unsatisfiable():
    """A screen too small to ever place a point min_distance away from the
    cat must not loop forever -- it should give up after max_attempts and
    still return a point inside the rect."""
    rng = random.Random(21)
    x, y = pick_spawn_position(
        0, 0, 10, 10, cat_x=5, cat_y=5, rng=rng, min_distance=10000.0, max_attempts=20
    )
    assert 0 <= x <= 10
    assert 0 <= y <= 10


def test_spawn_position_is_deterministic_given_a_seeded_rng():
    a = pick_spawn_position(0, 0, 1920, 1080, cat_x=960, cat_y=540, rng=random.Random(77))
    b = pick_spawn_position(0, 0, 1920, 1080, cat_x=960, cat_y=540, rng=random.Random(77))
    assert a == b
