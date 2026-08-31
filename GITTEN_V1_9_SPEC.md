# Gitten v1.9 — quick command bar

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first. Keep updating it as you go, per the working agreement.

**Build in the order below — each part is testable on its own before wiring together, the same discipline v1.7 used for its multi-part build.**

---

## Part 1: Command parsing (pure, testable)

New module `commands.py`: `parse_command(text: str) -> tuple[str, str]` — lowercases and trims the input, splits on the first whitespace into `(command_name, remaining_argument_text)`. Empty input, a bare command with no argument, and a command with an argument should all parse sensibly (argument is `""` when there isn't one). No Qt, no git, no side effects — this is pure string handling, testable with plain string cases.

## Part 2: The initial command set

These handlers need access to already-existing app state (git log for streak/commits, the battery reading, the rename mechanism, the mouse-chase trigger), so they can't be fully Qt-free the way `commands.py`'s parsing is — use your judgment on where the dispatch table itself lives (`main.py` vs. a method on `GittenApp` vs. elsewhere) the same way you've made similar plumbing calls before (e.g. where `_show_context_menu`'s logic ended up). What matters is the command set and behavior, not the exact file layout:

| Command | Behavior |
|---|---|
| `streak` | Reply with the current streak (reuse `streak.py`, don't recompute the logic) |
| `commits` | Reply with today's commit count in the watched repo (reuse the existing `git log --since=midnight` logic already used by the stats menu) |
| `battery` | Reply with current battery percentage |
| `rename <name>` | Same effect as the tray's "Rename..." action, given the typed name directly instead of opening a dialog |
| `chase` | Manually trigger the mouse-chase minigame right now, bypassing the random spawn timer (reuse the existing spawn/chase machinery from v1.7, don't duplicate it) |
| `help` | Reply listing the available commands |
| `quit` | Quit the app, same as the tray's "Quit" action |
| *(anything unrecognized)* | A friendly "didn't understand that, try `help`" reply — never silently do nothing |

All replies (except `quit`, which just exits) display via the existing nudge/one-liner bubble mechanism — no new response-rendering needed, this is another case of an existing display mechanism getting a new trigger source, the same shape as v1.8's welcome-back message.

## Part 3: The popup window

New file `command_bar_window.py`: a small window with a single-line text input (`QLineEdit`), reusing the same transparent/always-on-top/frameless window-flag setup already established (copy from `KittenWindow`/`mouse_window.py`'s proven flags, don't re-derive). Appears near the cat's current position when summoned. Enter submits the typed text through `parse_command` + the Part 2 dispatch and then closes the bar; Escape closes it without submitting; losing focus (clicking elsewhere) also closes it — standard command-palette behavior. This window is self-contained and doesn't need to touch the cat window's own `view_mode`/click-handling state machine at all, since it's an entirely separate popup, not a mode of the existing window.

## Part 4: Global hotkey

Register a system-wide hotkey (suggest `Ctrl+Alt+G`) via the Windows `RegisterHotKey` API (`ctypes`/`pywin32`, consistent with this codebase's existing raw-win32-API style — don't add a new third-party hotkey library as a dependency). On the registered `WM_HOTKEY` message, show the command bar (Part 3) and give it keyboard focus. **Check the registration's return value and degrade gracefully if it fails** (e.g. another app already owns that combination) — log it, don't crash, matching every other win32-touching module's established discipline in this codebase. Since there's no settings panel yet, hardcoding the hotkey for now is fine — leave a comment noting it should become configurable once a settings UI exists.

## Testing

Unit tests for `parse_command` (empty input, bare command, command with argument, extra whitespace). Unit tests for each Part 2 handler where feasible without a live Qt app (mocking only what's necessary, and remember this codebase's own hard-won lesson about *not* monkeypatching compiled Qt/Shiboken methods — mock at the plain-Python boundary instead, the same way v1.8 mocked `get_idle_seconds` rather than anything Qt-internal). Live-test the popup window and global hotkey for real (summon it with the actual key combination, type a real command, confirm the real reply appears) — this project's established standard, not an off-screen assumption.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_9_SPEC.md`. Prompt (English): "Read GITTEN_V1_9_SPEC.md. Build in order: command parsing, then the command handlers, then the popup window, then the global hotkey — test each part before wiring the next. Test the hotkey and popup live, for real. Update DEVELOPMENT_NOTES.md and push when done."
