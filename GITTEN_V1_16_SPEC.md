# Gitten v1.16 — a genuine pixel-art redesign (Phase 4)

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first, in full, especially section 31 (v1.15) — that round's flat-mascot style is being fully replaced this round, not layered on top of. Keep updating the notes as you go, per the working agreement.

## What's actually changing, and why it's bigger than it sounds

This isn't a palette swap — it's two separate things happening together:
1. **How each pose is drawn**: a small, fixed logical pixel grid (hard-edged, flat-filled squares, no anti-aliasing) instead of smooth vector shapes.
2. **How poses animate**: real pixel-art characters typically animate via a small number of discrete frames swapped on a timer (like an old sprite sheet), not continuous smooth interpolation. This is a genuine technique change for anything that currently breathes/sways/drifts continuously.

**What does NOT need to change**: anything that's about *position over time* rather than *the character's own drawn frame* — the window's `walk_to` movement, the particle system's drift/fade, bubble entrance/fade timing. Those can keep their existing continuous timing exactly as-is; they just end up drawing a pixel-art-styled sprite at each moment instead of a vector one. Don't rebuild things that don't need rebuilding.

**Originality note**: this is inspired by the general pixel-art desktop-pet genre, not derived from or referencing any specific existing project — design original pixel art and an original grid/frame technique, don't reproduce anyone else's specific sprite designs, palette, or character names.

## Part 0: Technical foundation (build and verify this first, on the simplest possible test case, before any real pose)

- A small, fixed logical canvas — suggest 32×32 "pixels" for the cat (half that, 16×16, for the mouse, keeping the existing 2:1 canvas ratio the two sprites already have). Each logical pixel is a single flat-filled square, no gradients, no anti-aliasing.
- A simple, common technique for defining a frame: a small 2D grid where each cell maps to a color (a compact way to write pixel art in code — this general approach is standard/widespread, not tied to any specific project). Keep the per-character color palette deliberately small (roughly 4–6 colors total: body, outline/shadow, eye, one or two accent tones) — reuse `theme.ACCENT` as the body's primary color again, the same continuity principle v1.15 established.
- Rendering technique: draw each frame to a small off-screen `QImage`/`QPixmap` at the logical grid size using flat fills, then scale it up for display using **nearest-neighbor scaling** (`Qt.FastTransformation`, explicitly not `Qt.SmoothTransformation`) — this is what actually produces crisp, hard pixel edges instead of a blurry upscaled blob. Verify this specifically before building any real pose: render a simple placeholder grid (e.g. a few colored squares), scale it up, screenshot it, and confirm the edges are genuinely hard/blocky, not smoothed.
- Decide and document a simple frame-timing convention for discrete animation (e.g. a small fixed set of frame indices cycled every ~N milliseconds) that later parts can reuse consistently, the same "shared infrastructure built once" discipline the particle system and `theme.py` both established.

## Build the poses in this order — mirror v1.15's own sequencing exactly, verifying each with a real screenshot before moving on

1. **Body/idle pose only.** Get the grid technique, palette, and a basic idle animation (e.g. a simple 2-frame breathing or blink cycle) right on the simplest, most-seen pose first.
2. **Happy, waiting, deep-sleep faces.**
3. **Interaction poses**: sulking/reconciliation stages, hover-purr, high-five, focused, curious.
4. **Small chrome**: status badges, streak star/crown, seasonal accessories — these are small enough that they may need their own smaller grid or a simplified treatment (the same "these can't take the main character's own proportions literally" lesson v1.15's Part 4 already learned for outline width applies here too — decide the right scale for these deliberately, don't just reuse the cat's own grid size unchanged, and verify by actually rendering one before committing to a size).
5. **The mouse sprite.**

## Testing

Same as v1.15: overwhelmingly a real-screenshot round. For each part, capture real screenshots and confirm it genuinely reads as pixel art (hard edges, limited palette, visible discrete animation) rather than merely "smaller and blockier" vector shapes that still feel like the old style. At the end, regenerate `assets/demo.png`. Note plainly in `DEVELOPMENT_NOTES.md` whether the result genuinely achieves an authentic pixel-art feel or falls short of it — this is a real aesthetic bar to clear, not just a technical checklist.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_16_SPEC.md`. Prompt (English): "Read GITTEN_V1_16_SPEC.md and DEVELOPMENT_NOTES.md section 31 in full. Build and verify Part 0 (the technical foundation, especially nearest-neighbor scaling) in complete isolation first, then the 5 pose parts in order, each verified with a real screenshot before the next. Design original pixel art and an original frame technique -- don't reference or reproduce any specific existing project's sprites. Regenerate assets/demo.png at the end. Update DEVELOPMENT_NOTES.md and push when done."
