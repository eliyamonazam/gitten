# Gitten — a small addition: a hidden celebration command

A quick, self-contained round — not a new phase, just one small easter egg.

## What

Add an undocumented command to the command bar's existing dispatch table — not listed in `help`'s output, discoverable only by reading the source or guessing. Suggest `party` as the command word (your call if something else fits better).

When triggered: a short (~2s), self-clearing celebration — reuse the existing particle system (v1.5) for a burst of many colorful particles around the cat (more particles, varied colors, not just the usual sparkle tone), plus a brief version of the existing happy/high-five animation, plus a fun one-off message via the existing bubble mechanism (e.g. "🎉 you found it!"). No new rendering systems — this should be almost entirely recombining pieces that already exist.

## Testing

A small pure test that `party` is *not* present in the public `help` text/command list (confirming it stays undocumented) while still being dispatchable. Live-verify the visual burst the same way this project verifies everything visual.

## Handoff

"Add a small, undocumented `party` command to the command bar (not listed in help) that triggers a short celebratory particle burst plus a fun message, reusing the existing particle system and bubble display -- no new rendering code. Test that it's dispatchable but absent from help's text. Update DEVELOPMENT_NOTES.md and push when done."
