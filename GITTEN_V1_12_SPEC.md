# Gitten v1.12 — dashboard

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first, in full. Keep updating it as you go, per the working agreement.

## What this is

A single at-a-glance window, not editable configuration — a read-only view, unlike the settings panel. Reuses the same "normal window" precedent v1.11's `settings_window.py` established (`Qt.Window`, no transparency, no always-on-top, a real title bar) rather than reintroducing the overlay-style flags — this and the settings panel are the app's two normal windows, everything else stays an overlay.

## Trigger

Add "Dashboard..." to the tray menu (alongside "Settings...") and a `dashboard` command to the command bar's dispatch table, the same two-ways-in pattern every other window in this app already follows.

## Content

**Streak calendar**: a GitHub-contribution-style heatmap grid, the last ~10–12 weeks, one cell per day, shaded by that day's commit count (no commits = empty/light, more commits = more filled/intense — exact number of shade levels is your call). New pure function in `streak.py` (alongside the existing streak logic, not a new module): `commits_by_day(commit_dates, weeks=12) -> dict[date, int]`, built from the *same* `git log --format=%ad --date=short` data source `streak.py` already fetches — don't add a second, differently-shaped git query for this.

**Best streak ever**: a second new pure function, `longest_streak(commit_dates) -> int` — the longest run of consecutive days anywhere in the full commit history, not just the current one ending today (that's what the existing `streak.py` function already computes — this is a genuinely different calculation, not a rename of it). Show both current and best side by side.

**This week's commits**: a simple count, same `git log --since=...` style already used elsewhere in this codebase for "commits today," just widened to the start of the current week.

**System snapshot**: current battery/CPU/RAM/disk readings — reuse `system_monitor.py`'s existing reading functions directly, this is a display-only surface, no new monitoring logic.

**Pending reminders**: reuse the exact same list-building logic the settings panel's Reminders tab already has (sorted soonest-due) — this can be genuinely shared code between the two windows, not a second copy, your call on the cleanest way to share it (a small helper function, or the dashboard just re-parents/reuses the same widget-building code).

**Cat identity**: name, current mood/state in plain words, and how long the app has been running this session — small, but ties the whole thing together as "this is Gitten's status," not just a generic stats screen.

## Refresh

Unlike the settings panel (refresh-on-open is enough there, since it's edit-oriented), this should feel like a live status view: refresh periodically while the dashboard is visible. Piggyback on the existing ~7s system tick rather than adding a new timer — if the dashboard window is currently shown, have that tick also refresh its contents.

## Testing

Unit tests for the two new `streak.py` functions (`commits_by_day`: empty history, a history spanning fewer than the requested weeks, multiple commits on the same day counted correctly; `longest_streak`: empty, no gaps, one gap, best streak in the past rather than the most recent run — a case that would trip up an implementation that only ever looks at the current run). Live-verify the window the same way `settings_window.py` was: real screenshots of a real, populated dashboard, actually opened and inspected, not just internal-state assertions — this codebase has hit real rendering bugs twice now (v1.9's invisible command bar, v1.10/section-22's clipped nudge bubble) that only surfaced once someone actually looked at the pixels, so hold this new window to the same standard from the start rather than after a bug report. Also verify the periodic refresh actually updates visible content live (e.g. commit something in the watched repo while the dashboard is open, confirm the commits-this-week count changes without closing and reopening).

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_12_SPEC.md`. Prompt (English): "Read GITTEN_V1_12_SPEC.md and DEVELOPMENT_NOTES.md in full. Build the dashboard as a normal window (same precedent as settings_window.py), with the content sections described, refreshing periodically off the existing system tick while visible. Reuse existing data sources and the reminders list-building logic rather than duplicating them. Verify with real screenshots from the start. Update DEVELOPMENT_NOTES.md and push when done."
