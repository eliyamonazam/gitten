# Gitten v1.13 — a real design system, applied to Settings & Dashboard

This extends everything built so far. Read `DEVELOPMENT_NOTES.md` first, in full. Keep updating it as you go, per the working agreement.

## Why this round exists

Functionally this app is in good shape — the complaint driving this round is specifically that the visual side hasn't kept pace: `settings_window.py`/`dashboard_window.py` were built with zero styling (default Qt widget appearance), and nothing in this codebase has ever defined a shared color palette or visual language — every colored element so far (the alert amber, the heatmap greens, the cat's coral body, badge colors) was chosen locally, one feature at a time, with no central place tying them together. This round has two goals, in order: **define** a real, documented design system, then **apply** it to Settings and Dashboard specifically (the command bar/bubbles and the cat sprite itself are separate future rounds — don't touch their styling this round, so this stays reviewable in isolation).

## Part 1: Define the design system (do this before touching any window)

New module, `theme.py` — the single source of truth every future styling round (this one and the two to come) should pull from, the same "shared infrastructure built once" discipline the particle system established for the mouse-chase/drag-trail features.

**Audit before inventing**: look at every color already used across this codebase (the alert amber `#FFF3E0`/`#FB8C00`, the heatmap's green shades, the cat's `#E8935F` coral, the badge colors in `sprite.py`) before picking a palette — the goal is a *coherent* palette that these already-liked colors can belong to, not a wholesale replacement that makes the cat feel disconnected from the windows. Land on: a small set of named colors (a primary accent, one or two secondary accents, background/surface tones for a light theme, text colors with good contrast, and a reused-not-reinvented warning/alert tone), a consistent font family, and consistent spacing/corner-radius conventions (e.g. one standard button padding, one standard corner radius used everywhere rather than ad hoc numbers per widget). Document the palette with a short comment on *why* each color was chosen (e.g. "reuses the existing alert amber so warnings read consistently app-wide") — this file should be legible to a future session deciding whether a new color fits the system or not.

Express it as real, reusable Qt styling — a QSS stylesheet string (or a small set of them) that can be applied via `setStyleSheet`, plus any plain constants (hex colors, font family, spacing values) other code might need directly rather than parsing them back out of QSS.

## Part 2: Apply it to Settings and Dashboard

Both windows should look like they belong to the same considered, coherent app — not default Qt gray boxes. Concretely, using `theme.py`'s system:

- Buttons, tabs, list widgets, line edits, and the dashboard's info sections all take on the new palette and spacing/corner-radius conventions consistently — no leftover default-styled widgets sitting next to restyled ones.
- The dashboard's heatmap widget (`_HeatmapWidget`) keeps its own existing green shading logic (that's meaningful data-encoding, not decoration to be reskinned) but should sit comfortably within the new theme's surface/background colors rather than looking pasted onto a mismatched backdrop.
- Preserve every existing behavior exactly (this is a styling pass, not a functional change) — no tab, button, or field should work any differently than before.

## Testing

This round is almost entirely visual judgment, which unit tests can't meaningfully evaluate — hold it to this codebase's own established real-screenshot standard, but as the *primary* verification this time, not a supplement to unit tests the way it usually is. Capture real `QScreen.grabWindow` screenshots of both restyled windows, actually open and look at them, and compare side by side against the current `assets/settings.png`/`assets/dashboard.png` (captured just last round) to confirm this is a genuine, visible improvement — not a subtle tweak that happens to pass a diff. If anything about the result doesn't clearly read as more polished than the current screenshots, say so plainly in `DEVELOPMENT_NOTES.md` rather than declaring success by default.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_13_SPEC.md`. Prompt (English): "Read GITTEN_V1_13_SPEC.md and DEVELOPMENT_NOTES.md in full. Audit existing colors across the codebase, then define theme.py as described, then apply it to Settings and Dashboard only — leave the command bar, bubbles, and the cat sprite untouched this round. Verify with real screenshots compared against the current assets/settings.png and assets/dashboard.png. Update DEVELOPMENT_NOTES.md and push when done."
