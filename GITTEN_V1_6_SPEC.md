# Gitten v1.6 — curiosity reaction on new app launch

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first. Keep updating it as you go, per the working agreement.

## What "opening a program" means here

Not every new OS process — Windows constantly spawns invisible background/helper processes, and reacting to those would be noisy and meaningless. Instead: react when a **new process that owns a visible, titled top-level window** appears — that's the practical definition of "the user opened a program" (as opposed to some service starting in the background). This deliberately does *not* re-trigger for a new window/tab inside an already-running app (e.g. a new browser tab) since that doesn't create a new process in the tracked sense — only a genuinely new program launch does.

## 1. Detection

New thin I/O wrapper, alongside `foreground_window.py`'s existing style (e.g. `visible_windows.py`): enumerate all visible top-level windows with a non-empty title via `win32gui.EnumWindows` + `IsWindowVisible`, resolve each to its owning PID via `win32process.GetWindowThreadProcessId` (same call already used elsewhere in this codebase), and return the set of distinct PIDs. Exclude Gitten's own process (`os.getpid()`) from the result so it never reacts to itself.

New pure module `app_launch.py`, same discipline as every other pure module in this project (no Qt, no win32 imports, timestamps and PID sets passed in by the caller): a function taking the previous poll's PID set, the current poll's PID set, the last-reaction timestamp, `now`, and a cooldown (default 10s), returning whether to react this poll. Logic: a reaction is due if `current_pids - previous_pids` is non-empty AND `now - last_reaction_at >= cooldown` — the cooldown exists so opening several programs in quick succession (e.g. starting up a whole workspace at once) doesn't fire a reaction for each one individually.

Poll on the existing ~5–10s system-status timer in `main.py` rather than adding a new one — reuse, don't duplicate.

## 2. Reaction

A short (~2s), self-clearing "curiosity" animation — the familiar "boolean flag + `QTimer.singleShot` to clear it" idiom used throughout this codebase. Visually distinct from the existing `focused` (test/build) overlay even though both involve perked ears — e.g. add a brief head-tilt alongside the ear-perk, so it reads as "noticing something new" rather than "watching intently." Your call on the exact visual distinction, but it should be genuinely distinguishable side by side, not a near-duplicate of `focused`.

**Precedence**: sulking and the notification-inbox view suppress it, same as every other overlay (`turn_stage is None and view_mode == "pet"`). For precedence against `hovering`/`focused` specifically, use your own judgment the way v1.5's hover-vs-focused precedence was decided — make a reasonable call, verify it concretely (a pixel-diff or equivalent, not just reasoning about it), and document which way you went and why in `DEVELOPMENT_NOTES.md`.

## Testing

Unit tests for `app_launch.py`: no new PIDs → no reaction; a new PID present but still within cooldown → no reaction; a new PID present and cooldown elapsed → reaction; an empty previous set on first poll (don't treat "everything currently open" as N simultaneous new launches — the very first poll should just establish the baseline, not fire a reaction for every already-running app). Live-verify the win32 wrapper and the full wiring the same way this project's other Qt/win32 features have been (real event/window objects, not just off-screen reasoning) — this codebase has a consistent track record of catching real bugs this way rather than trusting off-screen renders alone, keep that up here too.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_6_SPEC.md`. Prompt (English): "Read GITTEN_V1_6_SPEC.md and implement the curiosity reaction. Pay attention to the first-poll baseline case so it doesn't fire for every already-running app on startup. Test live, not just off-screen. Update DEVELOPMENT_NOTES.md and push when done."
