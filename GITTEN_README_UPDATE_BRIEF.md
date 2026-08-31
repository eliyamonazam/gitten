# README overhaul brief

The README currently only documents v1 and v1.1 — everything from v1.2 onward (notification inbox, sulking/reconciliation, streak, focus mode, combo alert, one-liners + rare shooting star, hover purr, double-click high-five, drag sparkle trail, nameable cat, seasonal accessories, day/night palette) is undocumented for anyone browsing the repo. Rewrite the README to actually reflect the current app. Read `DEVELOPMENT_NOTES.md` in full for what to describe accurately — don't guess at behavior from memory of the specs alone, several things were adjusted or bug-fixed after the fact (e.g. the manual-verification bug fixes in section 14).

## Sections to cover

**Demo at top**: if you can capture a real screenshot or short screen recording of the live app (even just the kitten in its normal state plus maybe the stats menu open), replace or supplement the current placeholder with that — a real screenshot matters a lot more for a visual desktop app like this than it did for Wisp's CLI demo SVG. If that's not practical in your environment, leave a clear `<!-- TODO: replace with real screenshot -->` comment rather than silently skipping it.

**Feature list**: organize by category rather than one flat list, roughly:
- Git awareness (mood: idle/happy/waiting, daily commit streak)
- System awareness (battery/CPU/RAM/disk badges, low-battery + uncommitted-changes combo alert)
- Focus/productivity (distraction nudge, test/build focus reaction)
- Notifications (Windows notification inbox — note the one-time permission grant it needs)
- Personality & interaction (sulking/reconciliation, hover purr, double-click high-five, draggable with a sparkle trail, random one-liners, the rare shooting-star event)
- Personalization (renaming, birthday accessory, Halloween/Yalda accessories, day/night palette)

For each, one or two lines is enough — this is a feature list, not a tutorial.

**Configuration**: there are now several places a user might want to customize behavior (watched repo, distraction app list, test/build process list, cat name, birthday) — document where each lives (`~/.gitten/...` JSON files vs. tray menu prompts vs. `QSettings`) so it's discoverable without reading source.

**Project structure**: regenerate this section from the actual current file tree (`src/gitten/`, `tests/`, `scripts/`), not by editing the old one — it's been wrong before after past feature rounds. Get it directly from the filesystem, not from memory of the specs.

**A short "how it's built" note**: worth one short paragraph on the layering principle this codebase leans on — mood (git-driven), status badges (system-driven), distraction/focus, and attention/sulking are all independent overlay layers rather than one big state machine, which is why e.g. the cat can be happy *and* show a low-battery badge *and* be mid-reconciliation all at once. This is a genuinely nice piece of architecture and worth surfacing to anyone reading the code, not just buried in dev notes.

**Roadmap**: replace the old one. Telegram integration is *in progress*, not unstarted — the standalone connection-test script and secure credential handling exist (see `scripts/`), but it's not wired into the main app yet, blocked on the user obtaining API credentials from Telegram's own site. State that accurately rather than listing it as a future idea. Beyond that, list whatever's still genuinely deferred (check each spec's "explicitly deferred" section and DEVELOPMENT_NOTES.md for anything not yet done — e.g. pass/fail-aware test reactions, a full settings UI, live notification updates via `NotificationChanged`, GitHub Actions/CI reactions, decay during an interrupted reconciliation).

**Version number**: bump `pyproject.toml`'s version to reflect the amount of work since 0.2.0, using your judgment for what's reasonable (this has grown well past a "point release" at this point).

## After the README

Commit this as its own commit (not mixed with any code change), push, and update `DEVELOPMENT_NOTES.md` noting the README was brought up to date, same as the housekeeping note from the earlier session.
