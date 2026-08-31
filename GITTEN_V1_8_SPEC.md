# Gitten v1.8 — real keyboard/mouse idle detection

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first. Keep updating it as you go, per the working agreement.

## What this is (and isn't)

The existing git-driven `idle` mood means "no git activity for a while" — it says nothing about whether the user is actually sitting at the computer. This feature adds a second, independent signal: real system-wide keyboard/mouse inactivity, via the standard Windows `GetLastInputInfo` API (`user32.dll`, via `ctypes` — a well-known, simple technique, no new integration category; same complexity class as the existing `psutil`/`win32gui` wrappers already in this codebase).

This isn't just a new visual state — its real value is letting several *already-built* features stop firing when nobody's actually there to see them (see "Suppression" below). Treat that as equally important as the new sleep pose, not an afterthought.

## 1. Detection (thin I/O wrapper)

New module `system_idle.py` (Qt-free, matching `system_monitor.py`'s "thin wrapper, no decision logic" spirit): a function returning system idle time in seconds via `GetLastInputInfo`. Poll on the existing ~5–10s system-status timer already in `main.py` — don't add a new one.

## 2. Pure logic

Alongside `system_idle.py` or wherever fits: `is_away(idle_seconds, threshold_seconds=600) -> bool` (default 10 minutes) — deliberately kept as a simple binary state, not graduated levels; this codebase's other binary gates (sulking, focus, etc.) have worked fine as simple booleans and there's no clear need for more granularity here.

## 3. A real "deep sleep" pose

New visual state in `sprite.py`, distinct from the existing git-driven idle pose (closed eyes + "zzz") — e.g. the cat lies down rather than sits, with a slower/deeper version of the existing breathing sine-wave. This should read as visibly different from regular idle side by side, the same bar already applied to distinguishing `focused` from the new v1.6 curiosity reaction.

**Precedence — your call, but document the reasoning**: does `AWAY` override the mood display entirely (deep-sleep regardless of whether the cat would otherwise be happy/waiting/sulking), or layer alongside it? Given the point of this state is "nobody is here to see any of this," a full override toward deep-sleep seems more sensible than layering — but decide for real, verify it concretely (the same pixel-diff-or-equivalent standard this codebase has used for every other precedence decision, not just reasoning about it), and record which way you went and why in `DEVELOPMENT_NOTES.md`, the same as v1.5's purr-vs-focused and v1.6's curious-vs-focused decisions.

## 4. Suppression (the actually-useful part)

While `AWAY`, suppress three existing behaviors that are pointless with nobody watching — add `is_away` as one more argument to each existing gate function rather than duplicating logic:
- `should_spawn_mouse` (`mouse_game.py`)
- `should_show_oneliner` / the rare shooting-star roll (`oneliners.py`)
- the v1.6 curiosity reaction's own gate

Each of these already has a consistent "AND together every condition" shape — add the new one the same way, and update each function's existing tests to cover the new gating condition rather than only adding new tests.

## 5. Welcome-back note (small, optional polish)

When idle transitions back from `AWAY` to active after a long absence (e.g. 30+ minutes), show one short friendly bubble via the existing nudge/one-liner display mechanism — no new rendering needed, this is purely a new trigger for something that already exists.

## Testing

Unit tests for `is_away` (below/at/above threshold, custom threshold). Update the existing test suites for `should_spawn_mouse`, `should_show_oneliner`, and the curiosity gate to cover the new `is_away` condition — don't leave those partially tested. Live-verify the `GetLastInputInfo` wrapper and the full wiring (genuinely stop touching the mouse/keyboard for long enough to observe the transition, the same live-testing standard this project has held since v1.1) rather than trusting it from reasoning alone.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_8_SPEC.md`. Prompt (English): "Read GITTEN_V1_8_SPEC.md and implement real idle detection, including the suppression changes to should_spawn_mouse, should_show_oneliner, and the curiosity gate — that part matters as much as the new sleep pose. Decide and document the mood-override precedence per the spec. Test live, not just off-screen. Update DEVELOPMENT_NOTES.md and push when done."
