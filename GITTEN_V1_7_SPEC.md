# Gitten v1.7 — mouse chase minigame

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first. Keep updating it as you go, per the working agreement.

**Heads-up: this is a bigger feature than recent rounds** — it's the first one where the cat moves autonomously across the screen and where a second small entity (the mouse) needs to exist somewhere else on screen at the same time. Every individual piece reuses a technique already proven elsewhere in this codebase (see each section), but there are more moving parts than usual. Build in the order below — each part is testable on its own before wiring them together.

---

## Part 1: Autonomous walk (foundation — build and verify this first, on its own)

`window.py` currently only moves via user drag. Add a second way to move: `walk_to(target_x, target_y, on_arrived=None)`, which animates the window's position from wherever it currently is toward the target over time, using the existing ~30fps repaint timer to step a few pixels closer each frame (the same timer already driving breathing/tail-sway/particles — don't add a second one). Once within a small threshold distance of the target, snap exactly to it and call `on_arrived` if given.

**If the user manually drags the cat while it's auto-walking, the drag wins** — starting a real drag (`mousePressEvent`) should immediately cancel any in-progress `walk_to`, the same way user input should always take priority over an autonomous animation.

Test this part in complete isolation before touching anything else: command a real `KittenWindow` to `walk_to` a fixed point and confirm it actually arrives (position converges, `on_arrived` fires once), and confirm a mid-walk drag cancels it.

## Part 2: A second small window for the mouse

New file `mouse_window.py`: a small transparent/always-on-top widget, reusing the *exact* window-flag setup already established for `KittenWindow` in v1 (`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus`, `Qt.WA_TranslucentBackground`, `Qt.WA_ShowWithoutActivating`) — no new window-flag research needed, copy what already works. It doesn't need dragging, click handling, or any of `KittenWindow`'s interaction logic; it just displays a simple mouse (rodent) sprite at a given screen position and can be shown/hidden.

**Mouse sprite** (new `_draw_mouse` function, alongside `paint_kitten` in `sprite.py` or a small sibling module — your call): a simple gray rodent shape in the same minimal QPainter-primitives style as the kitten (small oval body, a thin curved tail, two small round ears, two dot eyes) — doesn't need its own animation states, a single static (or gently breathing, reusing that existing sine-wave idiom) pose is enough.

## Part 3: Spawn timing (pure logic)

New pure module `mouse_game.py`, same discipline as every other pure module here (no Qt, timestamps injected): a random-interval spawn timer similar in shape to `oneliners.py`'s (injectable RNG, testable bounds), but on its own cadence — default somewhere in the 45–90 minute range, your call on the exact numbers. Gate spawning behind the same suppression rules already used elsewhere (not sulking, not inbox view, not already mid-chase) plus one new one: not while the user is actively dragging the cat.

Spawn position: a random point within the current screen's available geometry (excluding the taskbar, same source `default_position()` already uses), far enough from the cat's current position to be worth chasing (pick a reasonable minimum distance).

## Part 4: Wiring it together

On spawn: show the mouse window at the chosen position, then call the cat window's `walk_to(mouse_x, mouse_y, on_arrived=...)`. On arrival ("caught"): hide the mouse window, play a small catch effect reusing the existing particle system (Feature 1 from v1.5 — a little poof/burst of particles at the catch point, the same system already used for the drag trail and shooting star, no new drawing code needed), then `walk_to` back to wherever the cat was *before* the chase started (save that position before the first `walk_to` call) so the cat's saved/anchored position isn't permanently disturbed by the game.

If the user drags the cat away mid-chase (cancelling the walk per Part 1's rule), just hide the mouse window immediately rather than leaving it stranded on screen with nothing chasing it.

## Testing

Unit tests for `mouse_game.py`'s spawn-timing function, same shape as the existing `oneliners.py` tests (bounds over many seeded draws, determinism, gating conditions). Live-test Parts 1–2 independently as described above before wiring, then live-test the full sequence: trigger a spawn, confirm the mouse window appears at the expected position, confirm the cat's window position actually converges toward it over successive frames, confirm arrival triggers the catch effect and the mouse window disappearing, and confirm the cat returns to its original position afterward. Also confirm a mid-chase drag cancels cleanly (mouse window hidden, no leftover walk animation fighting the drag).

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_7_SPEC.md`. Prompt (English): "Read GITTEN_V1_7_SPEC.md. Build and verify Part 1 (autonomous walk) in isolation first, then Part 2 (mouse window) on its own, then wire Parts 3–4 together per the spec. Test live at each stage, not just off-screen. Update DEVELOPMENT_NOTES.md as you go and push when done."
