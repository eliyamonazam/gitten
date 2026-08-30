from gitten.attention import (
    PETS_TO_RECONCILE,
    SULK_THRESHOLD_SECONDS,
    AttentionState,
    AttentionTracker,
    turn_stage,
)


def test_turn_stage_boundaries():
    assert turn_stage(-3) == 0
    assert turn_stage(0) == 0
    assert turn_stage(1) == 1
    assert turn_stage(2) == 2
    assert turn_stage(3) == 3
    assert turn_stage(4) == 4
    assert turn_stage(99) == 4


def test_default_state_is_normal():
    tracker = AttentionTracker()
    assert tracker.state == AttentionState.NORMAL
    assert tracker.pets_received == 0


def test_tick_without_prior_interaction_seeds_the_clock_and_stays_normal():
    tracker = AttentionTracker()
    assert tracker.tick(now=1000.0) == AttentionState.NORMAL
    assert tracker.last_interaction_at == 1000.0


def test_neglect_under_threshold_stays_normal():
    tracker = AttentionTracker(last_interaction_at=0.0)
    assert tracker.tick(now=SULK_THRESHOLD_SECONDS - 1) == AttentionState.NORMAL


def test_neglect_past_threshold_starts_sulking():
    tracker = AttentionTracker(last_interaction_at=0.0)
    assert tracker.tick(now=SULK_THRESHOLD_SECONDS) == AttentionState.SULKING
    assert tracker.pets_received == 0


def test_register_interaction_resets_the_clock_in_any_state():
    tracker = AttentionTracker(last_interaction_at=0.0)
    tracker.register_interaction(now=500.0)
    assert tracker.last_interaction_at == 500.0
    assert tracker.tick(now=500.0 + SULK_THRESHOLD_SECONDS - 1) == AttentionState.NORMAL


def test_register_interaction_does_not_count_as_a_pet_while_sulking():
    tracker = AttentionTracker(last_interaction_at=0.0)
    tracker.tick(now=SULK_THRESHOLD_SECONDS)
    assert tracker.state == AttentionState.SULKING

    tracker.register_interaction(now=SULK_THRESHOLD_SECONDS + 5)

    assert tracker.pets_received == 0
    assert tracker.state == AttentionState.SULKING


def test_pets_while_sulking_progress_through_stages_without_reconciling_early():
    tracker = AttentionTracker(last_interaction_at=0.0)
    tracker.tick(now=SULK_THRESHOLD_SECONDS)

    for expected in (1, 2, 3):
        tracker.register_pet(now=SULK_THRESHOLD_SECONDS + expected)
        assert tracker.pets_received == expected
        assert tracker.state == AttentionState.SULKING


def test_fourth_pet_fully_reconciles():
    tracker = AttentionTracker(last_interaction_at=0.0)
    tracker.tick(now=SULK_THRESHOLD_SECONDS)

    for _ in range(PETS_TO_RECONCILE):
        tracker.register_pet(now=SULK_THRESHOLD_SECONDS)

    assert tracker.state == AttentionState.NORMAL
    assert tracker.pets_received == 0


def test_no_decay_partial_reconciliation_holds_steady():
    tracker = AttentionTracker(last_interaction_at=0.0)
    tracker.tick(now=SULK_THRESHOLD_SECONDS)
    tracker.register_pet(now=SULK_THRESHOLD_SECONDS)

    # Lots of time passes with no further pets -- per the spec's v1.2
    # simplification, it should just wait at the partial stage.
    for _ in range(5):
        assert tracker.tick(now=SULK_THRESHOLD_SECONDS + 10_000) == AttentionState.SULKING
    assert tracker.pets_received == 1


def test_pet_while_normal_is_a_no_op_pet_but_still_an_interaction():
    tracker = AttentionTracker(last_interaction_at=0.0)
    tracker.register_pet(now=10.0)
    assert tracker.state == AttentionState.NORMAL
    assert tracker.pets_received == 0
    assert tracker.last_interaction_at == 10.0
