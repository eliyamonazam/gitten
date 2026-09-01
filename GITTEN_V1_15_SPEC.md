# Gitten v1.15 — the cat/mouse art, redrawn in a bold flat mascot style

This extends everything built so far, especially `theme.py`. Read `DEVELOPMENT_NOTES.md` first, in full. Keep updating it as you go, per the working agreement.

## Scope

Phase 3, the last of the visual-polish plan (Settings/Dashboard was Phase 1, the command bar/bubbles were Phase 2). This one is bigger than either of those — it touches every drawn pose of the cat and the mouse, not one or two windows — so it's broken into parts below. Build and verify each part before moving to the next, the same discipline v1.7 and v1.9 already used for their own multi-part builds.

## The style, defined once, applied everywhere

A bold, flat mascot look — closer to a modern app icon character (think the confident, simplified silhouettes of mascots like Duolingo's owl) than the current soft/glossy blob:

- **Outline**: every shape (body, ears, tail, limbs, eyes, mouth, accessories) gets a bold, uniform outline — one consistent stroke color and width used everywhere, not varying stroke weights per element. Use `theme.py`'s darkest text color for the outline, and pick one stroke width (in the sprite's existing 128-unit coordinate space) and hold it constant across every shape and every pose.
- **Fill**: flat, single-tone color. **No gradients, no soft highlight overlay** — this deliberately replaces the original v1 body's radial-gradient "glossy" treatment; that's an intentional style change, not something to preserve out of habit.
- **Primary color**: the cat's body color becomes `theme.ACCENT` (the same coral used throughout Settings/Dashboard/command bar/bubbles) instead of its own independent coral value — this is the last piece that ties the character itself into the same palette as the rest of the app, closing the loop Phase 1/2 started.
- **Eyes/face**: simplified geometric shapes, flat-filled, bold-outlined, consistent with the rest — your call on exact shapes as long as they hold to "bold and simple" rather than the current small-and-detailed treatment (tiny highlight dots, thin soft curves).
- Every existing *pose and animation timing* stays exactly as it is now — breathing, tail-sway, the eye/mouth shapes per mood, particle effects, all unchanged in behavior. Only how each shape is drawn changes, not when or why.

## Build in this order, verifying each with real screenshots before moving on

1. **Body/ears/tail base shape + the neutral idle pose only.** Get the style right on the simplest, most-seen pose first. Screenshot it, compare side by side against the current `assets/demo.png`, confirm it genuinely reads as the new style before touching anything else.
2. **The other mood faces**: happy, waiting, deep-sleep.
3. **Interaction poses**: the sulking/reconciliation stages, the hover-purr face, the high-five pose.
4. **Small chrome pieces**: the status badges, the streak star/crown icon, the seasonal accessories (birthday/Halloween/Yalda hats).
5. **The mouse sprite** (v1.7) — same style rules, its own small palette choice is your call, but it should read as belonging to the same visual world as the restyled cat.

## Testing

Overwhelmingly a real-screenshot round, the same as Phases 1 and 2 — unit tests don't meaningfully evaluate this. For each part above, capture real screenshots (use the full-screen-grab-and-crop technique v1.14 documented for this sandbox's layered-window screenshot limitation, rather than re-discovering it) and compare against the current assets before moving to the next part. At the end, regenerate `assets/demo.png` (the same off-screen-`QPixmap` contact-sheet technique used originally) so the README's demo reflects the new art, and note in `DEVELOPMENT_NOTES.md` whether this genuinely reads as a cohesive, improved character across every pose — not just that each individual screenshot looks fine in isolation.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_15_SPEC.md`. Prompt (English): "Read GITTEN_V1_15_SPEC.md and DEVELOPMENT_NOTES.md in full. Redraw the cat/mouse art in the bold flat mascot style described, building and verifying each of the 5 parts in order with real screenshots before moving to the next. Preserve every existing animation timing and pose exactly -- only the drawing style changes. Regenerate assets/demo.png at the end. Update DEVELOPMENT_NOTES.md and push when done."
