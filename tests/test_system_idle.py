from gitten.system_idle import DEFAULT_AWAY_THRESHOLD_SECONDS, is_away


def test_below_threshold_is_not_away():
    assert is_away(599.0, threshold_seconds=600.0) is False


def test_at_threshold_is_away():
    assert is_away(600.0, threshold_seconds=600.0) is True


def test_above_threshold_is_away():
    assert is_away(601.0, threshold_seconds=600.0) is True


def test_zero_idle_is_not_away():
    assert is_away(0.0) is False


def test_default_threshold_is_ten_minutes():
    assert DEFAULT_AWAY_THRESHOLD_SECONDS == 600.0


def test_custom_threshold_below():
    assert is_away(29.0, threshold_seconds=30.0) is False


def test_custom_threshold_at_and_above():
    assert is_away(30.0, threshold_seconds=30.0) is True
    assert is_away(45.0, threshold_seconds=30.0) is True
