# Gitten v1.5 — interactive & time-based personality features

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first. Keep updating it as you go, per the working agreement.

**Process note, same as v1.4: 7 features below, go through them IN THE ORDER LISTED, one at a time — implement, test, document in `DEVELOPMENT_NOTES.md`, then move on. The order isn't arbitrary: features 1–3 deliberately build on each other (a shared particle system), so don't skip ahead or reorder them. Commit each feature separately, not as one big commit.**

---

## Feature 1: Sparkle particle system (foundation for 2 and 3)

Build a small, generic reusable piece: a list of fading particles (position, spawn time, maybe a drift direction), pruned each frame (drop anything older than its lifespan, e.g. ~0.5–1s), drawn as small fading dots/sparkles in `paintEvent` using the existing ~30fps repaint timer. Keep this generic (not hardcoded to "drag trail" specifically) since Feature 3 reuses it for a different visual (a streak/trail effect for a shooting star) — a `spawn_particle(x, y)` / `update_and_prune(now)` / `draw_particles(painter)` shape is enough; no need for a full physics system.

## Feature 2: Sparkle trail while dragging

`window.py` already tracks a `_dragging` state (used for the existing move-vs-click disambiguation). While dragging, spawn a particle (Feature 1) at the current cursor position every couple of frames, so a fading sparkle trail follows the cat as it's moved. Purely cosmetic — no new state beyond what Feature 1 already provides.

## Feature 3: Rare random event (shooting star)

Extend the existing one-liner timer (`oneliners.py` / `_on_oneliner_timer` in `main.py`): each time it fires and `should_show_oneliner(...)` returns `True`, add a small chance (~5%, e.g. `rng.random() < 0.05`, using the same injectable-RNG idiom already established in `oneliners.py`) that instead of a normal text bubble, a "shooting star" plays instead — a single particle (reuse Feature 1's system) launched from one corner of the window and animated diagonally across it over ~1 second, fading as it goes. Add a pure `should_show_rare_event(rng, probability=0.05) -> bool` function to `oneliners.py`, tested the same way `should_show_oneliner` already is (seeded RNG, bounds check over many draws).

## Feature 4: Purr on hover

Use Qt's `enterEvent` / `leaveEvent` on the cat's widget region to track a `hovering: bool`. While hovering: ears do a small gentle wiggle (a slow oscillation, reusing the sine-wave idiom already used for breathing/tail sway) and the eyes shift to a content, slightly-squinted look, distinct from the mood-driven happy/idle/waiting faces — this is a separate overlay, the same way `focused` (v1.4 Feature 2) is layered independently of mood.

**Precedence, following the same pattern already established for `focused`**: purring is suppressed while sulking (`turn_stage is not None`) and while in the notification-inbox view — compute a single `show_purr = hovering and turn_stage is None and view_mode == "pet"` and use it consistently, the same style `show_focused` already uses.

## Feature 5: High-five on double-click

**Read this before implementing — there's a real conflict to resolve, the same category of issue already solved once for inbox-vs-pet clicks:** a double-click is, at the Qt event level, still two single clicks first. Without care, this would both open the notification inbox (or register two pets while sulking) AND trigger the high-five. Resolve it with the standard single/double-click disambiguation pattern: on mouse release, don't act immediately — start a short timer (~250ms, matching the OS's usual double-click interval, `QApplication.doubleClickInterval()` if convenient) before treating it as a single click (open inbox / register a pet). If a genuine double-click arrives within that window, cancel the pending single-click action and trigger the high-five instead. Apply this disambiguation consistently to both existing single-click behaviors (inbox-open and pet-registration), not just bypass it for one of them.

The high-five itself: a short (~1–1.5s) self-clearing animation state (the same "boolean flag + `QTimer.singleShot` to clear it" idiom already used several times, e.g. for the v1.3 Telegram alert lifecycle) where the cat raises one paw.

## Feature 6: Nameable cat

New tray menu entry, "Rename...", using a simple `QInputDialog.getText` prompt, saved via `QSettings` (same settings object already used for window position etc.). Use the name in: the tray icon's tooltip, and as a header line in the existing right-click stats menu (e.g. "— {name} —" above the existing Streak/Commits-today/battery lines). Default to "Gitten" if never set. Don't touch `oneliners.py`'s text list for this — keep the name substitution local to the menu/tooltip, not worth threading through every string.

## Feature 7: Seasonal accessories & day/night palette

**Two small pure functions, testable independently:**
- `seasonal_accessory(today: date) -> str | None` in a new small module (or alongside `streak.py` — your call), returning `"halloween"` (Oct 31), `"yalda"` (~Dec 21), `"birthday"` (if a birthday was set — see below), or `None`. Keep the occasion list to these three for now; more can be added later the same way.
- `is_night_time(hour: int) -> bool` — a simple range check (e.g. 23:00–7:00).

**Birthday**: add a second new tray menu entry, "Set my birthday...", alongside Feature 6's "Rename..." (both are simple one-time `QSettings`-backed prompts — natural to build together). A `QInputDialog` date entry is fine.

**Rendering**: the seasonal accessory renders as a small hat/icon sitting on top of the head — visually distinct from the existing badge (top-left) and streak (top-right) corner icons, since a hat reads as "worn" rather than "floating beside," so there's no collision with the existing icon slots. For day/night: when `is_night_time` is true, shift the body's base color toward a cooler, dimmer tone (a simple blend toward a "moonlit" hue) — a rendering-time adjustment, no new state stored.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_5_SPEC.md`. Prompt (English): "Read GITTEN_V1_5_SPEC.md. It has 7 features — go through them in the exact order listed (1–3 share a particle system, so don't reorder them), testing and documenting each in DEVELOPMENT_NOTES.md before moving to the next. Pay close attention to Feature 5's single/double-click disambiguation section. Commit each feature separately, then push to origin/main."
