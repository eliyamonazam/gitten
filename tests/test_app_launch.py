from gitten.app_launch import DEFAULT_COOLDOWN_SECONDS, should_react_to_new_launch


def test_no_new_pids_does_not_react():
    assert not should_react_to_new_launch(
        previous_pids={1, 2}, current_pids={1, 2}, last_reaction_at=None, now=100.0
    )


def test_pids_disappearing_does_not_react():
    assert not should_react_to_new_launch(
        previous_pids={1, 2}, current_pids={1}, last_reaction_at=None, now=100.0
    )


def test_new_pid_within_cooldown_does_not_react():
    assert not should_react_to_new_launch(
        previous_pids={1},
        current_pids={1, 2},
        last_reaction_at=95.0,
        now=100.0,
        cooldown=10.0,
    )


def test_new_pid_after_cooldown_reacts():
    assert should_react_to_new_launch(
        previous_pids={1},
        current_pids={1, 2},
        last_reaction_at=80.0,
        now=100.0,
        cooldown=10.0,
    )


def test_new_pid_with_no_prior_reaction_reacts():
    assert should_react_to_new_launch(
        previous_pids={1}, current_pids={1, 2}, last_reaction_at=None, now=100.0
    )


def test_cooldown_boundary_is_inclusive_of_elapsed():
    assert should_react_to_new_launch(
        previous_pids={1},
        current_pids={1, 2},
        last_reaction_at=90.0,
        now=100.0,
        cooldown=10.0,
    )


def test_empty_previous_set_on_first_poll_does_not_react():
    """The very first poll has nothing to compare against -- an empty
    previous set must establish the baseline, not treat every currently
    running program as a simultaneous new launch."""
    assert not should_react_to_new_launch(
        previous_pids=set(),
        current_pids={1, 2, 3, 4, 5},
        last_reaction_at=None,
        now=100.0,
    )


def test_default_cooldown_constant_is_ten_seconds():
    assert DEFAULT_COOLDOWN_SECONDS == 10.0
