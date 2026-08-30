"""Pure logic for the "focus" reaction (tests/builds running). No Qt, no
psutil -- easy to unit test, following the same pattern as ``distraction.py``.

``matches_focus_process`` decides whether a single process's command line
looks like one of the watched dev-tool invocations; ``load_focus_substrings``
reads the user-editable JSON list from ``~/.gitten/``, the same
JSON-file-in-``~/.gitten/`` pattern ``distraction.py`` already uses. The
actual sweep over running processes (``psutil.process_iter()``) is the real
system I/O and lives in ``system_monitor.py`` instead, same "thin I/O
boundary" split already used for ``foreground_window.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_FOCUS_SUBSTRINGS = [
    "pytest",
    "npm test",
    "npm run build",
    "cargo test",
    "go test",
]

DEFAULT_FOCUS_CONFIG_PATH = Path.home() / ".gitten" / "focus_config.json"


def matches_focus_process(cmdline: str, substrings: list[str] | None = None) -> bool:
    """Case-insensitive substring match of a process's command line against
    the watched list."""
    watched = substrings if substrings is not None else DEFAULT_FOCUS_SUBSTRINGS
    cmdline_lower = cmdline.lower()
    return any(s.lower() in cmdline_lower for s in watched if s)


def load_focus_substrings(path: Path = DEFAULT_FOCUS_CONFIG_PATH) -> list[str]:
    """Load the user-editable list of watched command-line substrings from a
    JSON file, e.g.::

        {"substrings": ["pytest", "npm test", ...]}

    Falls back to the shipped defaults if the file is missing or invalid.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [str(s) for s in data.get("substrings", DEFAULT_FOCUS_SUBSTRINGS)]
    except (OSError, ValueError, AttributeError):
        return list(DEFAULT_FOCUS_SUBSTRINGS)
