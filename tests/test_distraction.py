import json

from gitten.distraction import (
    DEFAULT_DISTRACTING_PROCESSES,
    DEFAULT_DISTRACTING_TITLES,
    DistractionTracker,
    is_distracting_window,
    load_distraction_lists,
)


def make_tracker(threshold_seconds=1200.0):
    return DistractionTracker(threshold_seconds=threshold_seconds)


# -- is_distracting_window --------------------------------------------------


def test_matches_distracting_process_exactly_case_insensitive():
    assert is_distracting_window("Discord.EXE", "General - My Server")


def test_does_not_match_unrelated_process():
    assert not is_distracting_window("notepad.exe", "untitled.txt")


def test_matches_distracting_title_substring_case_insensitive():
    assert is_distracting_window("chrome.exe", "(3) YouTube - Google Chrome")


def test_partial_process_name_does_not_match():
    # exact match on process name, not substring
    assert not is_distracting_window("mydiscord.exe", "some window")


def test_custom_lists_override_defaults():
    assert is_distracting_window(
        "slack.exe", "general", distracting_processes=["slack.exe"]
    )
    assert not is_distracting_window(
        "discord.exe", "general", distracting_processes=["slack.exe"], distracting_titles=[]
    )


# -- DistractionTracker ------------------------------------------------------


def test_short_distraction_does_not_nudge():
    t = make_tracker(threshold_seconds=1200.0)
    assert t.update(True, now=0.0) is False
    assert t.update(True, now=600.0) is False


def test_crossing_threshold_fires_one_nudge():
    t = make_tracker(threshold_seconds=1200.0)
    t.update(True, now=0.0)
    assert t.update(True, now=1200.0) is True
    assert t.update(True, now=1201.0) is False


def test_streak_reset_when_foreground_stops_matching():
    t = make_tracker(threshold_seconds=1200.0)
    t.update(True, now=0.0)
    assert t.update(False, now=500.0) is False
    assert t.streak_start is None
    # a fresh streak needs the full threshold again, not the leftover time
    t.update(True, now=600.0)
    assert t.update(True, now=1799.0) is False
    assert t.update(True, now=1800.0) is True


def test_long_binge_nudges_again_every_threshold_period():
    t = make_tracker(threshold_seconds=1200.0)
    t.update(True, now=0.0)
    assert t.update(True, now=1200.0) is True
    assert t.update(True, now=2000.0) is False
    assert t.update(True, now=2400.0) is True
    assert t.update(True, now=3600.0) is True


def test_not_distracting_never_nudges():
    t = make_tracker(threshold_seconds=1200.0)
    for now in range(0, 5000, 500):
        assert t.update(False, now=float(now)) is False


# -- load_distraction_lists --------------------------------------------------


def test_load_missing_file_returns_defaults(tmp_path):
    titles, processes = load_distraction_lists(tmp_path / "does_not_exist.json")
    assert titles == DEFAULT_DISTRACTING_TITLES
    assert processes == DEFAULT_DISTRACTING_PROCESSES


def test_load_valid_file_overrides_defaults(tmp_path):
    config = tmp_path / "distraction_config.json"
    config.write_text(
        json.dumps({"titles": ["9gag"], "processes": ["steam.exe"]}), encoding="utf-8"
    )
    titles, processes = load_distraction_lists(config)
    assert titles == ["9gag"]
    assert processes == ["steam.exe"]


def test_load_invalid_json_falls_back_to_defaults(tmp_path):
    config = tmp_path / "distraction_config.json"
    config.write_text("not valid json", encoding="utf-8")
    titles, processes = load_distraction_lists(config)
    assert titles == DEFAULT_DISTRACTING_TITLES
    assert processes == DEFAULT_DISTRACTING_PROCESSES
