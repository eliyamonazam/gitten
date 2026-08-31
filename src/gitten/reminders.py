"""Pure logic for text-command reminders (v1.10): duration parsing, which
reminders are due, id assignment, and reply formatting -- plus the JSON
load/save I/O boundary, kept in the same file rather than split out, the
same "pure decision + a small file-I/O boundary side by side" shape
`distraction.py` (matching logic + `load_distraction_lists`) and
`telegram_config.py` (`load_config`/`save_config`) already established.
No Qt anywhere in this file.

**A deliberate clock choice worth calling out**: every other pure module
in this codebase (`mood.py`, `attention.py`, `distraction.py`, ...) is fed
`time.monotonic()` by its caller, since monotonic time is what those
modules' short-lived, in-memory-only timers need. Reminders are different
-- they're persisted to disk and must still make sense after the app (or
the whole machine) restarts, and `time.monotonic()`'s origin is arbitrary
per-process and means nothing across a restart. So every `now`/`due_at`
timestamp that flows through this module is real wall-clock time
(`time.time()`), not monotonic time -- the caller (`main.py`) is
responsible for passing the right one in, the same "inject the clock"
discipline every other pure module already uses, just with a different
clock for a concrete, documented reason.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

GITTEN_DIR = Path.home() / ".gitten"
DEFAULT_REMINDERS_PATH = GITTEN_DIR / "reminders.json"

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)([smh])$")
_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0}

REMIND_USAGE_REPLY = "usage: remind <duration> <message> (e.g. remind 10m take a break)"
CANCEL_USAGE_REPLY = "usage: cancel <id> (see `reminders` for pending ids)"


@dataclass
class Reminder:
    id: int
    message: str
    due_at: float
    created_at: float


# -- parsing ----------------------------------------------------------------


def parse_duration(text: str) -> tuple[float | None, str]:
    """The first whitespace-separated token of `text` must be a number
    immediately followed by `s`/`m`/`h` (no space inside the token, no other
    units) -- e.g. `10s`, `5m`, `2h`. Returns `(seconds, remaining_text)` on
    a match, `(None, text)` otherwise. Same "pure parsing returns a tuple"
    shape as `commands.parse_command`, deliberately -- this is the same
    convention, not a new one.
    """
    parts = text.split(maxsplit=1)
    if not parts:
        return None, text
    match = _DURATION_RE.match(parts[0])
    if not match:
        return None, text
    value = float(match.group(1))
    unit = match.group(2)
    remaining = parts[1] if len(parts) > 1 else ""
    return value * _UNIT_SECONDS[unit], remaining


# -- scheduling / lookup ------------------------------------------------


def next_reminder_id(reminders: list[Reminder]) -> int:
    """The next id to assign -- one past the highest id currently in the
    list (0 if empty). Recomputed from the current list rather than kept as
    a separately-tracked counter, the same "recompute rather than track a
    running counter that can drift" idiom `streak.py`/`count_commits_today`
    already use, and it means a cancelled id is never reused by accident."""
    return max((r.id for r in reminders), default=0) + 1


def create_reminder(id: int, message: str, seconds: float, now: float) -> Reminder:
    return Reminder(id=id, message=message, due_at=now + seconds, created_at=now)


def due_reminders(reminders: list[Reminder], now: float) -> list[Reminder]:
    """Which reminders are due -- `due_at <= now` (exact-boundary inclusive)."""
    return [r for r in reminders if r.due_at <= now]


# -- reply formatting ---------------------------------------------------


def format_duration(seconds: float) -> str:
    """Same hours/minutes/seconds "largest non-zero unit(s)" shape as
    `GittenApp._format_uptime`, reused here (as its own pure function) for
    both the `remind` confirmation and the `reminders` listing's remaining
    time."""
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_set_reply(message: str, seconds: float) -> str:
    return f'Reminder set: "{message}" in {format_duration(seconds)}'


def format_reminders_list(reminders: list[Reminder], now: float) -> str:
    if not reminders:
        return "No pending reminders."
    ordered = sorted(reminders, key=lambda r: r.due_at)
    parts = [
        f'#{r.id} "{r.message}" ({format_duration(r.due_at - now)} left)' for r in ordered
    ]
    return "; ".join(parts)


def format_due_reply(reminder: Reminder) -> str:
    return f'⏰ {reminder.message}'


def format_flushed_reminders_reply(due: list[Reminder]) -> str:
    """The reply for reminders that came due while AWAY and are only being
    shown now, at the away->active transition -- see main.py's
    `_flush_due_reminders`."""
    joined = "; ".join(r.message for r in due)
    plural = "s" if len(due) != 1 else ""
    return f"while you were away, {len(due)} reminder{plural} came due: {joined}"


def format_cancel_reply(reminder: Reminder) -> str:
    return f'Cancelled reminder #{reminder.id} ("{reminder.message}").'


def format_cancel_unknown_reply(id_text: str) -> str:
    return f"No pending reminder with id '{id_text}'."


# -- persistence (~/.gitten/reminders.json) ----------------------------


def _reminder_to_dict(r: Reminder) -> dict:
    return {"id": r.id, "message": r.message, "due_at": r.due_at, "created_at": r.created_at}


def _reminder_from_dict(d: dict) -> Reminder:
    return Reminder(
        id=int(d["id"]),
        message=str(d["message"]),
        due_at=float(d["due_at"]),
        created_at=float(d["created_at"]),
    )


def load_reminders(path: Path = DEFAULT_REMINDERS_PATH) -> list[Reminder]:
    """Load the persisted reminder list, or `[]` if the file is missing or
    invalid -- same degrade-gracefully discipline as `telegram_config.
    load_config` / `distraction.load_distraction_lists`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [_reminder_from_dict(item) for item in data]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def save_reminders(reminders: list[Reminder], path: Path = DEFAULT_REMINDERS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([_reminder_to_dict(r) for r in reminders]), encoding="utf-8"
    )
