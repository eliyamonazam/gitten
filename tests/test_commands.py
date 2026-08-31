from gitten.commands import (
    COMMANDS_HELP_TEXT,
    UNKNOWN_COMMAND_REPLY,
    format_battery_reply,
    format_chase_reply,
    format_commits_reply,
    format_rename_reply,
    format_streak_reply,
    parse_command,
)


# -- parse_command ----------------------------------------------------------


def test_empty_input():
    assert parse_command("") == ("", "")


def test_whitespace_only_input():
    assert parse_command("   ") == ("", "")


def test_bare_command_no_argument():
    assert parse_command("streak") == ("streak", "")


def test_bare_command_with_trailing_whitespace():
    assert parse_command("  streak  ") == ("streak", "")


def test_command_with_argument():
    assert parse_command("rename Whiskers") == ("rename", "whiskers")


def test_command_with_extra_internal_whitespace():
    assert parse_command("  rename   Bob  ") == ("rename", "bob")


def test_uppercase_command_is_lowercased():
    assert parse_command("STREAK") == ("streak", "")


def test_argument_with_multiple_words():
    assert parse_command("rename big fat cat") == ("rename", "big fat cat")


# -- format_streak_reply ------------------------------------------------


def test_streak_reply_with_value():
    assert format_streak_reply(5) == "Streak: 5 day(s)"


def test_streak_reply_zero():
    assert format_streak_reply(0) == "Streak: 0 day(s)"


def test_streak_reply_none():
    assert format_streak_reply(None) == "Streak: -- (no repo watched)"


# -- format_commits_reply -------------------------------------------------


def test_commits_reply_with_value():
    assert format_commits_reply(3) == "Commits today: 3"


def test_commits_reply_none():
    assert format_commits_reply(None) == "Commits today: -- (no repo watched)"


# -- format_battery_reply -------------------------------------------------


def test_battery_reply_with_value():
    assert format_battery_reply(87.4) == "Battery: 87%"


def test_battery_reply_none():
    assert format_battery_reply(None) == "Battery: n/a"


# -- format_rename_reply ----------------------------------------------------


def test_rename_reply_with_name():
    assert format_rename_reply("whiskers") == "Got it -- I'm whiskers now!"


def test_rename_reply_no_name():
    assert format_rename_reply("") == "usage: rename <name>"


# -- format_chase_reply -----------------------------------------------------


def test_chase_reply_default():
    assert format_chase_reply() == "here I go!"


def test_chase_reply_already_chasing():
    assert format_chase_reply(already_chasing=True) == "already on the hunt!"


# -- constants ----------------------------------------------------------


def test_help_text_mentions_every_command():
    for name in ("streak", "commits", "battery", "rename", "chase", "help", "quit"):
        assert name in COMMANDS_HELP_TEXT


def test_unknown_command_reply_mentions_help():
    assert "help" in UNKNOWN_COMMAND_REPLY
