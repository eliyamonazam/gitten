# Project-wide housekeeping brief (post v1.6–v1.12)

The last full README pass was after v1.5 (see the earlier "Housekeeping: README overhaul" entry in `DEVELOPMENT_NOTES.md`). Everything since — curiosity reactions, the mouse-chase minigame, real idle detection, the command bar, reminders, the settings panel, and the dashboard — is undocumented for anyone browsing the repo. Read `DEVELOPMENT_NOTES.md` in full before writing anything, the same standard every spec since v1.10 has already held itself to, not just the most recent sections.

## README

**Feature list**: regenerate rather than append. Given how much this app can now do, consider whether grouping by *how you interact with it* reads better than the existing pure-category grouping — this app now has a real second mode beyond ambient reactions: things you actively invoke (the command bar and its commands, the settings panel, the dashboard) versus things that happen on their own (mood, badges, curiosity, sulking, the mouse-chase spawn, etc.). Use your judgment on the best structure; the goal is that someone skimming the README actually understands the app has both an ambient-companion side and a real assistant-tool side, not that it reads as one long undifferentiated list.

**Command bar section**: needs its own clear callout — the hotkey, and the full current command list (`streak`, `commits`, `battery`, `rename`, `chase`, `help`, `quit`, `remind`, `reminders`, `cancel`, `settings`, `dashboard`) with one line each. Pull the authoritative list from `commands.py`'s actual dispatch table / `COMMANDS_HELP_TEXT`, not from memory of the specs — several commands were added after the original v1.9 spec.

**Windows**: the app now has two genuinely different kinds of window worth explaining plainly — the overlay-style ones (the cat, the mouse, the command bar popup: frameless, transparent, always-on-top) and the two normal ones (Settings, Dashboard: real title bars, ordinary window behavior). This distinction is real architecture, not a cosmetic detail — it's already called out in `DEVELOPMENT_NOTES.md` for both `settings_window.py` and `dashboard_window.py`, worth surfacing here too.

**Configuration**: update to reflect that most of what used to require hand-editing `~/.gitten/*.json` files now has a real UI in Settings — mention the settings panel as the primary way to configure things now, while noting the underlying files still exist for anyone who prefers editing them directly.

**"How it's built" architecture paragraph**: this already exists from the last README pass (the independent-overlay-layers principle: mood/badges/distraction/attention as separate layers). Consider whether it's worth a short addition about the command-bar pattern (one dispatch table, thin per-command glue, real logic in pure modules) as a second architectural principle worth naming — your call whether that's genuinely additive or would just pad the section; don't force it if the existing paragraph already reads fine.

**Project structure**: regenerate completely from the actual current file tree, not by editing the previous version — this section has been stale after every past round that didn't regenerate it from scratch (see the v1.5-era README overhaul's own notes about this).

**Screenshots**: `assets/demo.png` (the kitten mood/state contact sheet) is still accurate for the cat itself, no need to redo it. But Settings and Dashboard are real, substantial parts of the app now and aren't represented anywhere visually — if practical in your environment, capture a screenshot of each (real `QScreen.grabWindow`, the same standard already used for verifying those windows during their own build sessions) and add them near wherever the README describes those features. If that's not practical this session, leave a clear `<!-- TODO -->` rather than skipping silently, same as last time.

**Roadmap**: rewrite from a real check, not memory. Grep every spec's "explicitly deferred" section plus anything `DEVELOPMENT_NOTES.md` itself flagged as a known gap or simplification, and list what's genuinely still open. Telegram integration's status is unchanged since it was last documented — still blocked on the user obtaining API credentials, still just the standalone connection-test script and config/list persistence, `telegram_watcher.py` still doesn't exist. State that plainly, don't let it quietly disappear from the roadmap just because many rounds have passed since it was last touched.

## Version

Bump `pyproject.toml`'s version again, using your judgment the same way you did last time — this has grown substantially since 0.6.0.

## After

Commit this as its own commit, separate from any code change, push, and update `DEVELOPMENT_NOTES.md` noting the README/version were brought current, same as the last housekeeping round.
