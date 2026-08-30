# Gitten v1.4 — streaks, focus mode, combo alert, random one-liners

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first. Keep updating it as you go, per the working agreement.

**Important process note: this file has 4 independent features. Go through them ONE AT A TIME, in order. For each one: implement it, test it, write its section in `DEVELOPMENT_NOTES.md`, and only then move to the next. Do not attempt all 4 at once and do not skip any — if one turns out harder than expected, say so in the notes and still move on to the others rather than abandoning the rest of the file.**

---

## Feature 1: Daily commit streak

Compute the current consecutive-day streak of commits in the watched repo — don't maintain a running counter that could drift; recompute from `git log` each time, the same idiom already used for `count_commits_today`. Get commit dates via `git log --format=%ad --date=short`, dedupe to distinct days, and count backward from today (or yesterday, if nothing's been committed yet today) for as long as each preceding day also has a commit. One gap breaks the streak.

New pure module `streak.py`: a function taking a list/set of commit-date strings and returning the streak length as an int — no Qt, no subprocess, fully unit-testable with fake date lists (empty list, single day, broken streak, streak including today vs. ending yesterday, etc.).

Rendering (additive to `sprite.py`, same optional-parameter pattern as before): a small icon above the head once the streak reaches a threshold — nothing below 3 days, a small star at 3–6, a bigger/gold star at 7–29, a small crown at 30+. Also add the current streak number to the existing right-click stats menu.

## Feature 2: Focus reaction while tests/builds run

Detect whether a matching process is currently running via `psutil.process_iter()`, checking each process's command line against a small **user-configurable** list of substrings (default: `["pytest", "npm test", "npm run build", "cargo test", "go test"]`), same JSON-file-in-`~/.gitten/` pattern as the distraction list.

**Be upfront about a real limitation, don't try to work around it with something fragile**: since Gitten only *observes* these processes rather than launching them itself, it cannot reliably know whether the run passed or failed — only whether one is currently running. So this feature is a "focused/watching" reaction only (e.g. ears perked, intent staring animation) for as long as a matching process is running, returning to normal the moment it's gone. Do not attempt to guess pass/fail from log files or exit codes; that would need Gitten to wrap and launch the command itself, which is a bigger feature for a future round, not this one.

## Feature 3: Verify (and lightly enhance) the low-battery + uncommitted-changes combo

Because `mood.py` (git-driven) and `status_badge.py` (system-driven) were deliberately built as independent layers from the start, the case of `mood == WAITING` and a low/critical battery badge both being true at the same time should already render both together with **no new code** — confirm this is actually true by triggering both conditions at once (e.g. in a quick manual/headless check) rather than assuming.

If confirmed working: add one small deliberate touch so this specific combination reads as more urgent than either alone — e.g. swap the single "!" in the waiting speech bubble for "‼" specifically when a low/critical battery badge is also active at that moment, purely as a rendering-time check, no new state machine needed.

## Feature 4: Random cute one-liners

Reuse the existing nudge bubble mechanism in `window.py` (`show_nudge` / the opacity fade timeline already built for the distraction nudge) — it already does exactly "show a bubble with this text for ~4 seconds," so this feature is mostly about *scheduling*, not new rendering.

Pick a random interval between 45–90 minutes for the next one-liner. Only actually show it if the cat is currently in normal idle "pet" view (not sulking, not mid-Telegram-alert, not already showing another nudge, not in the notification inbox view) — skip and reschedule rather than interrupting something else.

Ship a starter list of short, friendly, programmer-flavored one-liners in Persian (matching the tone of the existing nudge message). A few examples to match the tone — add several more in the same spirit:
- "یادت نره وقفه بگیری 🙂"
- "کدت امروز قشنگه"
- "یه فنجون چای چطوره؟"
- "commit کوچیک، خوشحالی بزرگ"

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_4_SPEC.md`. Prompt (English): "Read GITTEN_V1_4_SPEC.md. It has 4 features — go through them one at a time, in the order listed, testing and documenting each in DEVELOPMENT_NOTES.md before moving to the next. Commit each feature separately rather than all at once, then push to origin/main."
