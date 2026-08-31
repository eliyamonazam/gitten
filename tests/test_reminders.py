from gitten.reminders import (
    CANCEL_USAGE_REPLY,
    DEFAULT_REMINDERS_PATH,
    GITTEN_DIR,
    REMIND_USAGE_REPLY,
    Reminder,
    create_reminder,
    due_reminders,
    format_cancel_reply,
    format_cancel_unknown_reply,
    format_due_reply,
    format_duration,
    format_flushed_reminders_reply,
    format_reminder_row,
    format_reminders_list,
    format_set_reply,
    load_reminders,
    next_reminder_id,
    parse_duration,
    save_reminders,
    sorted_by_due,
)

# -- parse_duration -----------------------------------------------------


def test_parse_duration_seconds():
    assert parse_duration("10s take a break") == (10.0, "take a break")


def test_parse_duration_minutes():
    assert parse_duration("5m stretch") == (300.0, "stretch")


def test_parse_duration_hours():
    assert parse_duration("2h check the oven") == (7200.0, "check the oven")


def test_parse_duration_no_message():
    assert parse_duration("10m") == (600.0, "")


def test_parse_duration_missing_unit():
    assert parse_duration("10 take a break") == (None, "10 take a break")


def test_parse_duration_non_numeric():
    assert parse_duration("soon take a break") == (None, "soon take a break")


def test_parse_duration_empty_string():
    assert parse_duration("") == (None, "")


def test_parse_duration_unsupported_unit():
    assert parse_duration("10d take a break") == (None, "10d take a break")


def test_parse_duration_space_inside_token_not_allowed():
    assert parse_duration("10 m take a break") == (None, "10 m take a break")


def test_parse_duration_decimal_value():
    assert parse_duration("1.5h nap") == (5400.0, "nap")


# -- due_reminders --------------------------------------------------------


def _r(id_, due_at):
    return Reminder(id=id_, message=f"msg{id_}", due_at=due_at, created_at=0.0)


def test_due_reminders_none_due():
    reminders = [_r(1, 100.0), _r(2, 200.0)]
    assert due_reminders(reminders, now=50.0) == []


def test_due_reminders_some_due():
    reminders = [_r(1, 50.0), _r(2, 200.0)]
    assert due_reminders(reminders, now=100.0) == [reminders[0]]


def test_due_reminders_exact_boundary_is_due():
    reminders = [_r(1, 100.0)]
    assert due_reminders(reminders, now=100.0) == reminders


def test_due_reminders_empty_list():
    assert due_reminders([], now=100.0) == []


# -- next_reminder_id / create_reminder -----------------------------------


def test_next_reminder_id_empty():
    assert next_reminder_id([]) == 1


def test_next_reminder_id_increments_past_highest():
    assert next_reminder_id([_r(1, 0.0), _r(5, 0.0), _r(3, 0.0)]) == 6


def test_create_reminder():
    reminder = create_reminder(id=1, message="take a break", seconds=600.0, now=1000.0)
    assert reminder == Reminder(id=1, message="take a break", due_at=1600.0, created_at=1000.0)


# -- formatters -----------------------------------------------------------


def test_format_duration_seconds_only():
    assert format_duration(45) == "45s"


def test_format_duration_minutes_and_seconds():
    assert format_duration(90) == "1m 30s"


def test_format_duration_hours_and_minutes():
    assert format_duration(3660) == "1h 1m"


def test_format_duration_never_negative():
    assert format_duration(-5) == "0s"


def test_format_set_reply():
    assert format_set_reply("take a break", 600.0) == 'Reminder set: "take a break" in 10m 0s'


def test_format_reminders_list_empty():
    assert format_reminders_list([], now=0.0) == "No pending reminders."


def test_format_reminders_list_sorted_by_due_time():
    reminders = [_r(2, 200.0), _r(1, 100.0)]
    text = format_reminders_list(reminders, now=0.0)
    assert text.index("#1") < text.index("#2")


def test_sorted_by_due_orders_soonest_first():
    reminders = [_r(2, 200.0), _r(1, 100.0), _r(3, 300.0)]
    assert [r.id for r in sorted_by_due(reminders)] == [1, 2, 3]


def test_sorted_by_due_empty_list():
    assert sorted_by_due([]) == []


def test_format_reminder_row_contains_id_message_and_remaining():
    row = format_reminder_row(_r(7, 160.0), now=100.0)
    assert row == '#7 "msg7" (1m 0s left)'


def test_format_due_reply():
    reminder = _r(1, 100.0)
    assert "msg1" in format_due_reply(reminder)


def test_format_flushed_reminders_reply_singular():
    text = format_flushed_reminders_reply([_r(1, 100.0)])
    assert "1 reminder came due" in text
    assert "msg1" in text


def test_format_flushed_reminders_reply_plural():
    text = format_flushed_reminders_reply([_r(1, 100.0), _r(2, 200.0)])
    assert "2 reminders came due" in text
    assert "msg1" in text and "msg2" in text


def test_format_cancel_reply():
    assert format_cancel_reply(_r(3, 0.0)) == 'Cancelled reminder #3 ("msg3").'


def test_format_cancel_unknown_reply():
    assert "'99'" in format_cancel_unknown_reply("99")


def test_usage_constants_mention_the_command():
    assert "remind" in REMIND_USAGE_REPLY
    assert "cancel" in CANCEL_USAGE_REPLY


# -- persistence ----------------------------------------------------------


def test_default_path_lives_under_gitten_dir():
    assert GITTEN_DIR.name == ".gitten"
    assert DEFAULT_REMINDERS_PATH.parent == GITTEN_DIR


def test_load_reminders_missing_file_returns_empty_list(tmp_path):
    assert load_reminders(tmp_path / "does_not_exist.json") == []


def test_load_reminders_invalid_json_returns_empty_list(tmp_path):
    path = tmp_path / "reminders.json"
    path.write_text("not valid json", encoding="utf-8")
    assert load_reminders(path) == []


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "nested" / "reminders.json"
    reminders = [
        Reminder(id=1, message="take a break", due_at=1600.0, created_at=1000.0),
        Reminder(id=2, message="stretch", due_at=1700.0, created_at=1100.0),
    ]
    save_reminders(reminders, path)

    assert load_reminders(path) == reminders


def test_save_reminders_creates_parent_directory(tmp_path):
    path = tmp_path / "a" / "b" / "reminders.json"
    save_reminders([], path)
    assert path.exists()
