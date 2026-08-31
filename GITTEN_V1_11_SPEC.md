# Gitten v1.11 — settings panel

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first, in full. Keep updating it as you go, per the working agreement.

## What this round is (and isn't)

This isn't a new feature so much as giving a real UI to configuration that already exists but currently requires either hand-editing JSON files in `~/.gitten/` or a one-off tray dialog. **Don't invent new configurability for things that were never configurable before** (badge thresholds, sulking/away timing, the hotkey combo, spawn intervals, etc.) — that's real scope creep for a future round, not this one. Scope is strictly: consolidate what already has a load/save path into one window.

**Architecturally, this is the first normal window in the app.** Every window so far (`KittenWindow`, `mouse_window.py`, `command_bar_window.py`) has deliberately used frameless/always-on-top/transparent/tool-window flags. The settings panel should **not** copy those — it's an ordinary `QDialog` or `QMainWindow` with a normal title bar, normal close/minimize behavior, not always-on-top, not click-through. Worth stating plainly so it doesn't get built by copying the wrong precedent.

## Trigger

Add "Settings..." to the tray menu. Also add a `settings` command to the command bar's dispatch table (consistent with how everything else is reachable multiple ways) that opens the same window.

## Structure: tabs, one per existing config surface

**General**: watched repo path (reuse the existing file-dialog flow, validate it's actually a git repo before accepting — same check the app already does at first-run), cat name, birthday. These three already have working apply-logic (`_apply_rename`, the birthday setter, the repo-chooser) — call that same logic from here rather than writing parallel save paths.

**Distraction list**: the titles/processes lists and the minute threshold, currently in `~/.gitten/distraction_config.json`. A simple list widget with add/remove for each list, a number field for the threshold.

**Focus (test/build) process list**: same shape as above, for the process-substring list `focus.py`/`system_monitor.py` reads.

**Telegram**: the favorites/bad-sender lists (`~/.gitten/telegram_lists.json`). Note in the UI (a short label is enough) that this configures who gets a reaction *once Telegram is connected* — the connection itself is still pending, per v1.3's status, and this round doesn't change that.

**Reminders**: not really "configuration," but it's the natural place to *view* pending reminders and cancel one via a button instead of only through the `reminders`/`cancel` commands — reuse the exact same cancel path `_handle_cancel_command` already calls, don't reimplement it here. Your call on refresh timing (e.g. refresh when this tab becomes visible is enough, no need for a live-updating timer).

## The part that actually matters most: changes must take effect live, not just on next restart

Several of these lists (distraction, focus, telegram) are currently loaded once at startup into in-memory state and never re-read afterward — check this for each one as you go. A settings panel that only edits the JSON file and leaves the running app using stale in-memory data until restart would be a hollow implementation of this feature; for every tab, after Save, both persist to disk **and** push the new value into whatever in-memory state the running app actually reads from, the same way `_apply_rename` already updates the live cat name immediately rather than requiring a restart. If a given list currently has no reload path, add one (a small `reload_from(...)` on whatever holds it, or just reassign the attribute directly from `main.py` — your call on the cleanest mechanism per case) rather than leaving that one tab's changes inert until the app restarts.

## Testing

This round is UI-heavy with less pure-logic material than most, and that's expected — don't force artificial pure-logic modules where the actual work is Qt glue and file I/O. Where real logic exists (e.g. repo-path validation), keep it in a small testable function the way this codebase always has. For the live-apply behavior specifically, live-verify it the way this project verifies everything Qt-related: change something in a tab, save, and confirm the *running app's actual behavior* reflects it immediately (e.g. edit the distraction list, then confirm the distraction-detection logic is now actually checking against the new list) — not just that the JSON file on disk changed.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_11_SPEC.md`. Prompt (English): "Read GITTEN_V1_11_SPEC.md and DEVELOPMENT_NOTES.md in full. Build the settings panel as a normal (non-transparent, non-topmost) window with the five tabs described. The live-apply requirement matters as much as the UI itself — check each config surface for whether it currently only loads at startup, and fix that where needed. Reuse existing apply/cancel logic rather than duplicating it. Test live. Update DEVELOPMENT_NOTES.md and push when done."
