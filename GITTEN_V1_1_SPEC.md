# Gitten v1.1 — system awareness & social nudge (feature addendum)

This extends `GITTEN_SPEC.md` (already implemented as v1 — see `DEVELOPMENT_NOTES.md` for what exists). Read those first for the current architecture (`mood.py`, `git_watcher.py`, `sprite.py`, `window.py`, `main.py`). This document only describes what's new and how it plugs into the existing structure — don't rebuild anything already working, extend it.

## Important architectural note: two independent overlay layers

The existing `mood.py` state machine (idle / happy / waiting) is driven ONLY by git activity and must stay that way — don't conflate it with the new signals below. Add a SEPARATE, independent "status badge" concept: a small icon rendered above/beside the kitten's head on top of whatever git-mood is currently showing. At most one status badge shows at a time, chosen by priority (see below), so the cat can be "happy" (just committed) and also show a low-battery badge at the same moment without conflict.

Add a new small pure-logic module, `status_badge.py`, following the exact same pattern as `mood.py`: no Qt imports, all inputs (battery %, plugged-in flag, cpu/mem/disk readings) passed in by the caller, not read internally — same reason as before, it's what makes it trivially unit-testable.

## 1. System status badges

New dependency: `psutil`.

Poll every ~5–10s (reuse the existing periodic `QTimer` pattern in `main.py`, or add a second lightweight timer).

| Signal | Condition | Badge |
|---|---|---|
| Critical battery | `battery.percent < 10` and not plugged in | Red battery icon, fast pulse |
| Low battery | `battery.percent < 20` and not plugged in | Orange battery icon, slow pulse |
| Charging | `battery.power_plugged` and `percent < 100` | Small lightning-bolt icon |
| High resource usage | rolling average of the last ~10 samples of `cpu_percent()` OR `virtual_memory().percent` > 85% (sustained, not a single spike) | Small sweat-drop icon, cat looks mildly strained |
| Low disk space | system drive `disk_usage(...).percent > 90` (or free space < 5 GB) | Small disk icon with a warning mark |

**Priority when several are true at once (show only one):** critical battery → low disk space → high resource usage → charging → low battery.

No badge at all is the common case when nothing crosses a threshold — this must not feel naggy.

## 2. Social media / distraction nudge

New dependency: `pywin32` (for `win32gui` / `win32process`) if not already present.

Detect the foreground window's process name and title via `win32gui.GetForegroundWindow()` + `win32process.GetWindowThreadProcessId()`. Many distracting sites run inside a browser tab rather than as a standalone app, so match on window title too, not just process name.

Ship a sensible, user-editable default list (a JSON file or `QSettings`-backed list is enough for v1.1 — a full settings UI can wait):
```
default_distracting_titles = ["instagram", "twitter", "x.com", "tiktok", "reddit", "youtube"]
default_distracting_processes = ["telegram.exe", "discord.exe"]
```
Case-insensitive substring match on the title; exact (case-insensitive) match on process name.

Track continuous time spent with a matching foreground window, resetting the counter the instant the foreground window stops matching. When the continuous streak crosses a threshold (default 20 minutes, easy to change later), trigger ONE gentle nudge:
- A short, non-blocking animation (the cat waves / taps) plus a small speech bubble near its head with a brief friendly line (e.g. "یه وقفه کوتاه چطوره؟") that fades on its own after ~4 seconds. Never a modal dialog, never steals focus, never blocks input.
- After a nudge fires, don't fire again until either the streak resets, or another full threshold period passes while still in a distracting app (so a long binge gets a nudge roughly every 20 minutes, not just once, ever).

Everything here is local-only — no network calls, nothing leaves the machine. Worth one line in the README so it's clearly not telemetry.

## 3. Right-click stats menu

Right-click anywhere on the kitten opens a small `QMenu` at the cursor position (dismisses on click-away like any normal context menu). Show, as quick-glance entries:

- Commits today in the watched repo — compute via `git log --since=midnight --oneline`, piped through `subprocess` the same way the rest of the app already shells out to git. Don't maintain a running counter; recomputing is simpler and stays correct even after a restart.
- Current battery percentage
- Watched repo name/path
- How long Gitten has been running this session (simple elapsed time since launch)

A real "Change watched repo" and "Quit" entry can also live here for discoverability, alongside (not instead of) the tray icon's existing versions.

Keep it to these four info lines for v1.1 — resist turning this into a dashboard; it's a glance, not a settings panel.

## Explicitly still out of scope
Everything already deferred in `GITTEN_SPEC.md`, plus from this round: Pomodoro/break reminders, real idle/sleep detection from keyboard+mouse activity, historical graphs for CPU/disk, reacting to test/build runs, multi-project support, day/night behavior, and a full settings UI (a JSON/QSettings list is enough for now).

## How to hand this to Claude Code
Put this file next to `GITTEN_SPEC.md` as `GITTEN_V1_1_SPEC.md`. Prompt: "Read GITTEN_V1_1_SPEC.md — this extends the existing app. Implement the three features described without changing `mood.py`'s existing behavior. Add unit tests for `status_badge.py` the same way `mood.py` is tested: pure logic, no Qt, all inputs passed in by the caller."
