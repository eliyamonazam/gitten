# README touch-up: the v1.13–v1.15 visual polish arc

Read `DEVELOPMENT_NOTES.md`'s sections 27, 30, and 31 (the three visual-polish rounds) before writing anything. This is a lighter round than the last full README overhaul — a touch-up, not a rewrite.

## What to add

- A short mention that the app now has a real, coherent design system (`theme.py`) — the cat's own body color, the command bar, every bubble type, and the Settings/Dashboard windows all share one palette now, rather than each surface inventing its own colors. A sentence or two is enough, doesn't need its own huge section.
- If the feature list or "how it's built" section describes the cat's appearance anywhere (soft/glossy, gradients, etc.), update that description to match the current bold flat mascot style — don't leave stale wording describing the pre-v1.15 look.
- `assets/demo.png` was already regenerated in place with the new art (same filename), so no image-reference change needed there.

## Version

Small bump in `pyproject.toml`, your judgment.

## After

Commit and push as usual, update `DEVELOPMENT_NOTES.md`.
