from datetime import datetime, timedelta, timezone

from gitten.notifications import format_notification

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_joins_multiple_text_lines():
    item = format_notification("Chrome", ["Extension updated", "Welcome to v4.1.0"], NOW, NOW)
    assert item.app_name == "Chrome"
    assert item.text == "Extension updated -- Welcome to v4.1.0"


def test_empty_lines_are_skipped():
    item = format_notification("App", ["", "Only this", ""], NOW, NOW)
    assert item.text == "Only this"


def test_no_text_at_all_falls_back_to_placeholder():
    item = format_notification("App", [], NOW, NOW)
    assert item.text == "(no text)"


def test_missing_app_name_falls_back_to_placeholder():
    item = format_notification(None, ["hi"], NOW, NOW)
    assert item.app_name == "Unknown app"


def test_time_text_just_now():
    created = NOW - timedelta(seconds=10)
    assert format_notification("App", ["x"], created, NOW).time_text == "just now"


def test_time_text_minutes_ago():
    created = NOW - timedelta(minutes=14)
    assert format_notification("App", ["x"], created, NOW).time_text == "14m ago"


def test_time_text_hours_ago():
    created = NOW - timedelta(hours=3, minutes=10)
    assert format_notification("App", ["x"], created, NOW).time_text == "3h ago"


def test_time_text_older_than_a_day_shows_a_date():
    created = NOW - timedelta(days=2)
    time_text = format_notification("App", ["x"], created, NOW).time_text
    assert time_text == created.astimezone().strftime("%b %d")
