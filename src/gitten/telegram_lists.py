"""Where the Telegram favorite/bad-sender lists live (~/.gitten/telegram_lists.json),
per `GITTEN_V1_3_SPEC.md`'s `{"favorites": [...], "bad": [...]}` shape -- pure
path/JSON logic, no Telethon import, same discipline as `telegram_config.py`
and `distraction.load_distraction_lists`.

This module didn't exist before v1.11: v1.3 only ever built the standalone
connection-test script and `telegram_config.py` (the api_id/api_hash cache);
`telegram_watcher.py` and the actual favorite/bad-sender matching were never
built, so nothing in the running app currently reads these lists back out at
runtime (see DEVELOPMENT_NOTES.md section 10/15). The v1.11 settings panel's
Telegram tab still needs a load/save path to let the lists be edited and
persisted ahead of that connection existing -- once `telegram_watcher.py` is
eventually built, it should read via `load_telegram_lists` here rather than
re-deriving the file location, the same "one source of truth for where a
config file lives" reasoning `telegram_config.py`'s own docstring already
gives for the credential/session paths.
"""

from __future__ import annotations

import json
from pathlib import Path

GITTEN_DIR = Path.home() / ".gitten"
DEFAULT_TELEGRAM_LISTS_PATH = GITTEN_DIR / "telegram_lists.json"


def load_telegram_lists(
    path: Path = DEFAULT_TELEGRAM_LISTS_PATH,
) -> tuple[list[str], list[str]]:
    """(favorites, bad) sender lists -- ([], []) if the file is missing or
    invalid, since there's no shipped default list for Telegram senders the
    way there is for the distraction/focus lists."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        favorites = [str(f) for f in data.get("favorites", [])]
        bad = [str(b) for b in data.get("bad", [])]
        return favorites, bad
    except (OSError, ValueError, AttributeError):
        return [], []


def save_telegram_lists(
    favorites: list[str], bad: list[str], path: Path = DEFAULT_TELEGRAM_LISTS_PATH
) -> None:
    """Persist the favorite/bad sender lists to the same JSON file
    `load_telegram_lists` reads back from."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"favorites": list(favorites), "bad": list(bad)}), encoding="utf-8"
    )
