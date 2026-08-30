from gitten.mood import Mood, MoodMachine


def make_machine(happy_seconds=4.0, waiting_threshold_seconds=1800.0):
    return MoodMachine(
        happy_seconds=happy_seconds,
        waiting_threshold_seconds=waiting_threshold_seconds,
    )


def test_starts_idle():
    m = make_machine()
    assert m.mood == Mood.IDLE


def test_commit_triggers_happy():
    m = make_machine()
    assert m.on_commit(now=0.0) == Mood.HAPPY


def test_happy_expires_to_idle_when_clean():
    m = make_machine(happy_seconds=4.0)
    m.on_commit(now=0.0)
    assert m.tick(now=2.0) == Mood.HAPPY
    assert m.tick(now=5.0) == Mood.IDLE


def test_dirty_change_under_threshold_stays_idle():
    m = make_machine(waiting_threshold_seconds=1800.0)
    assert m.update_dirty(True, now=0.0) == Mood.IDLE
    assert m.tick(now=1000.0) == Mood.IDLE


def test_dirty_change_over_threshold_becomes_waiting():
    m = make_machine(waiting_threshold_seconds=1800.0)
    m.update_dirty(True, now=0.0)
    assert m.tick(now=1800.0) == Mood.WAITING
    assert m.tick(now=5000.0) == Mood.WAITING


def test_cleaning_up_resets_to_idle():
    m = make_machine(waiting_threshold_seconds=1800.0)
    m.update_dirty(True, now=0.0)
    m.tick(now=1800.0)
    assert m.mood == Mood.WAITING
    assert m.update_dirty(False, now=1801.0) == Mood.IDLE


def test_commit_resets_waiting_streak():
    m = make_machine(waiting_threshold_seconds=1800.0, happy_seconds=4.0)
    m.update_dirty(True, now=0.0)
    m.tick(now=1800.0)
    assert m.mood == Mood.WAITING

    assert m.on_commit(now=1801.0) == Mood.HAPPY
    assert m.dirty_since is None
    assert m.is_dirty is False

    # After the celebration ends and nothing new is dirty, it settles to idle.
    assert m.tick(now=1801.0 + 4.0) == Mood.IDLE


def test_new_dirty_change_after_happy_expiry_starts_a_fresh_streak():
    m = make_machine(waiting_threshold_seconds=100.0, happy_seconds=4.0)
    m.on_commit(now=0.0)
    m.tick(now=5.0)  # happy expired -> idle
    m.update_dirty(True, now=10.0)
    assert m.tick(now=50.0) == Mood.IDLE  # only 40s of dirty time so far
    assert m.tick(now=111.0) == Mood.WAITING  # 101s of dirty time


def test_committing_while_still_happy_extends_happy():
    m = make_machine(happy_seconds=4.0)
    m.on_commit(now=0.0)
    assert m.on_commit(now=2.0) == Mood.HAPPY
    assert m.tick(now=5.0) == Mood.HAPPY  # extended to 2.0 + 4.0 = 6.0
    assert m.tick(now=6.5) == Mood.IDLE
