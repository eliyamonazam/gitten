# Gitten v1.14 — apply the design system to the command bar & bubbles

This extends everything built so far, especially v1.13's `theme.py`. Read `DEVELOPMENT_NOTES.md` first, in full. Keep updating it as you go, per the working agreement.

## Scope

Phase 2 of the visual-polish plan (Settings/Dashboard was Phase 1; the cat/mouse sprite art itself is Phase 3, a separate future round — don't touch `sprite.py`'s cat/mouse drawing this round). This round covers everything currently drawn with ad hoc colors instead of pulling from `theme.py`: the command bar popup, and every bubble type window.py renders (the regular nudge/one-liner bubble, and the distinct reminder-alert styling from `DEVELOPMENT_NOTES.md` section 22).

**Important constraint, unlike Phase 1**: Settings and Dashboard are QSS-styled widgets, but the command bar's input panel and every bubble are drawn with raw `QPainter` calls, not stylesheets. This is exactly why Phase 1 was asked to expose `theme.py`'s colors as plain constants alongside the QSS strings, not only as QSS — use those plain constants directly in the `QPainter` drawing code here, the same values, not a second set of hardcoded hex strings that happen to look similar.

## 1. Command bar

Re-style `command_bar_window.py`'s input panel (the background box added when the visibility bug was fixed) using `theme.py`'s palette, corner-radius, and spacing conventions instead of whatever colors were chosen at the time — it currently doesn't share a visual language with Settings/Dashboard at all.

## 2. Regular bubbles (nudge / one-liner)

Re-style using `theme.py`'s plain color/spacing constants. Preserve the existing entrance/fade timing behavior exactly — this is a visual reskin, not a behavior change.

## 3. Reminder-alert bubbles — preserve the distinction, don't erase it

The reminder-alert styling (amber, bold text, the clock icon, longer display duration) was deliberately built to look distinctly more urgent than a regular nudge, and `theme.py`'s Phase 1 palette was specifically told to *reuse* that existing amber as the system's one warning/alert tone rather than inventing a new color. Apply `theme.py` here in a way that reinforces that existing distinction (reminder alerts still clearly read as more urgent than regular bubbles, side by side) — don't accidentally flatten both bubble types toward the same look in the process of unifying the palette. If anything about applying the shared theme makes the two bubble types look too similar, that's worth flagging in `DEVELOPMENT_NOTES.md` rather than shipping quietly.

## Testing

Same standard as Phase 1: this is visual judgment, hold it to the real-screenshot standard as the primary verification. Capture real screenshots of the command bar and of each bubble type (regular nudge and a reminder alert, live-triggered the same way past sessions have done it — a real `remind 2s ...` command is the simplest way to get a real alert bubble on demand) and confirm side by side that: (a) the command bar and bubbles now visually belong to the same family as Settings/Dashboard, and (b) the reminder alert is still clearly distinguishable from a regular nudge. If either isn't true, say so plainly rather than declaring success by default, the same standard v1.13 already held itself to.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_14_SPEC.md`. Prompt (English): "Read GITTEN_V1_14_SPEC.md and DEVELOPMENT_NOTES.md in full. Apply theme.py's plain constants to the command bar panel and every bubble type via their existing QPainter drawing code -- don't touch sprite.py this round. Preserve the reminder-alert vs regular-nudge visual distinction explicitly. Verify with real screenshots, including a live-triggered reminder alert. Update DEVELOPMENT_NOTES.md and push when done."
