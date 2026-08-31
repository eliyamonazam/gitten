"""Pure command-bar logic (v1.9): parsing typed input and formatting the
reply text shown in the nudge bubble. No Qt, no git, no psutil -- same
"inject already-gathered data, keep I/O out" discipline as
`notifications.format_notification`. The actual data gathering (git log,
battery, cat-rename persistence, mouse-chase trigger) stays in main.py's
dispatch glue, since it genuinely needs already-existing app state
(git-watcher path, tray/settings, the KittenWindow instance) the same way
`GittenApp._stats_menu_lines` already does -- only the "what text to show"
decision is pulled out here where it's cleanly testable in isolation.
"""

from __future__ import annotations

COMMANDS_HELP_TEXT = "commands: streak, commits, battery, rename <name>, chase, help, quit"
UNKNOWN_COMMAND_REPLY = "didn't understand that, try `help`"


def parse_command(text: str) -> tuple[str, str]:
    """Lowercase and trim `text`, then split on the first whitespace into
    (command_name, remaining_argument_text). Empty input, a bare command
    with no argument, and a command with an argument all parse sensibly --
    the argument is "" when there isn't one.

    Note the whole input is lowercased, per spec, including any argument --
    so `rename Bob` becomes `("rename", "bob")`. This is a deliberate
    product decision, not an oversight -- see DEVELOPMENT_NOTES.md's v1.9
    section for the tradeoff this implies for `rename`.
    """
    normalized = text.strip().lower()
    if not normalized:
        return "", ""
    parts = normalized.split(maxsplit=1)
    command = parts[0]
    argument = parts[1] if len(parts) > 1 else ""
    return command, argument


def format_streak_reply(streak: int | None) -> str:
    if streak is None:
        return "Streak: -- (no repo watched)"
    return f"Streak: {streak} day(s)"


def format_commits_reply(commits: int | None) -> str:
    if commits is None:
        return "Commits today: -- (no repo watched)"
    return f"Commits today: {commits}"


def format_battery_reply(percent: float | None) -> str:
    if percent is None:
        return "Battery: n/a"
    return f"Battery: {percent:.0f}%"


def format_rename_reply(name: str) -> str:
    if not name:
        return "usage: rename <name>"
    return f"Got it -- I'm {name} now!"


def format_chase_reply(already_chasing: bool = False) -> str:
    if already_chasing:
        return "already on the hunt!"
    return "here I go!"
