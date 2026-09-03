# Gitten v1.17 — a bold-outline calico chibi redesign (Phase 5, replaces v1.16)

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first, in full, especially section 33 (v1.16) — this round fully replaces that pixel-art style, not layers on top of it, the same relationship v1.16 had to v1.15.

## The style, and why it's a bigger swing than v1.15→v1.16 was

Inspired by a general aesthetic direction — bold black outlines, patchy two-tone "calico" coloring, chibi proportions (a large head, a small simple body/paws beneath it), simple dot eyes — not copied from or referencing any specific existing character, creator, or franchise. Design an entirely original character in this general style.

This is a bigger change than the last swing in two ways:
1. **Back to smooth curves, not pixel grids.** v1.16 was deliberately blocky/discrete; this style is smooth `QPainterPath` curves again, closer to v1.15's *technique* — but with a much bolder, thicker outline and flat two-color-patch fills instead of v1.15's single flat color. Animation goes back to continuous smooth motion (breathing, sway) rather than v1.16's discrete frame-swapping — state that explicitly as a deliberate reversal, the same way v1.16 documented its own reversal of v1.15's technique.
2. **A real body and paws come back.** v1.15/v1.16 were a body+head+tail creature; this character has a large head with a small, simple chibi body and paws beneath it — closer to the original v1 proportions than either recent redesign, but restyled. This means the paw-dependent behaviors (high-five, the nudge wave) are natural again rather than needing reinterpretation. The deep-sleep/AWAY pose is a particularly good fit for this style's chibi-curled-up quality — lean into that rather than treating it as just another pose.

## Part 0: the style foundation

- **Outline**: much thicker and bolder than v1.15's `_OUTLINE_PEN_WIDTH` — this is a defining visual trait of the style, not a subtle bump. Pick a value and hold it uniform everywhere, the same "one width, no per-element overrides" discipline as before, just a visibly chunkier number this time.
- **Coloring**: flat, two-tone "calico" patches — a light base color (white/cream; audit `theme.py` for whether a suitable light surface tone already exists before inventing a new one, the same "audit before inventing" discipline v1.13 used) plus `theme.ACCENT` (the existing orange) as the patch color, placed asymmetrically (one ear a different color than the other, an off-center cheek/body patch) rather than symmetrically — asymmetry is part of what makes calico coloring read as charming rather than mechanical.
- **Face**: simple filled-circle dot eyes (no crescents, no pixel grid), a small simple mouth (your call on the exact shape — a simple curve reads as content/neutral, a small zigzag/scribble shape reads as a bit grumpy/impish, useful variation across moods), a few short whisker-mark lines near the cheek, soft blush-circle cheeks.
- **Body/paws**: small and simple relative to the head — chibi proportions, not a return to v1's more evenly-proportioned body.

## Build in this order, verifying each with a real screenshot before moving on (same discipline as v1.15/v1.16)

1. **Head/body/paw base shape + neutral idle pose.** Get the outline weight, patch coloring, and basic dot-eye face right on the simplest pose first.
2. **Happy, waiting, deep-sleep (AWAY) faces** — lean into the curled/chibi quality for deep-sleep specifically, per the note above.
3. **Interaction poses**: sulking/reconciliation stages, hover-purr, high-five (now a natural paw-raise again), focused, curious.
4. **Small chrome**: status badges, streak star/crown, seasonal accessories — restyle these to match the new bold-outline look too, rather than leaving them in v1.16's pixel style (a mixed-style app would undercut the whole point of a coherent redesign). Same lesson as before about not literally reusing the main character's own outline width at this much smaller scale — decide and verify a proportionate value.
5. **The mouse sprite** — same style family, its own small palette choice is your call.

## Testing

Same real-screenshot-primary standard as v1.15/v1.16. For each part, capture real screenshots and confirm it reads as the intended style (bold outline, patchy two-tone coloring, simple dot-eye charm) rather than a thicker-lined version of v1.15's look. At the end, regenerate `assets/demo.png`. Note plainly in `DEVELOPMENT_NOTES.md` whether the result genuinely achieves this style's specific charm or falls short — the same honest bar the last two rounds held themselves to.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_17_SPEC.md`. Prompt (English): "Read GITTEN_V1_17_SPEC.md and DEVELOPMENT_NOTES.md section 33 in full. This replaces v1.16's pixel-art style entirely. Build and verify the 5 parts in order with real screenshots. Design an original character in this general bold-outline calico chibi style -- don't reference or reproduce any specific existing character or creator's design. Regenerate assets/demo.png at the end. Update DEVELOPMENT_NOTES.md and push when done."
