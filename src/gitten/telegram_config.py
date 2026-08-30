"""Where Telegram credentials/session live, and how they're cached.

Zero Telethon imports here on purpose -- this is pure path/JSON logic, unit
testable the same way ``mood.py`` and ``distraction.py`` are, and shared by
both the standalone connection-test script and (later) ``telegram_watcher.py``
so there's exactly one place that decides where these files go.

Per the v1.3 spec, none of this may live inside the project folder: the
config and session both live under ``~/.gitten/``, the same directory
already used for ``distraction_config.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

GITTEN_DIR = Path.home() / ".gitten"
DEFAULT_CONFIG_PATH = GITTEN_DIR / "telegram_config.json"
# Telethon appends ".session" itself, so this points at the *stem*.
DEFAULT_SESSION_PATH = GITTEN_DIR / "telegram"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict | None:
    """Read cached ``{"api_id": ..., "api_hash": ...}``, or None if absent/invalid."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"api_id": int(data["api_id"]), "api_hash": str(data["api_hash"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_config(api_id: int, api_hash: str, path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Cache api_id/api_hash to disk, creating the parent directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"api_id": api_id, "api_hash": api_hash}),
        encoding="utf-8",
    )
