# Gitten v1.10 — reminders (built on the command bar)

This extends everything built so far, especially v1.9's command bar infrastructure — read `DEVELOPMENT_NOTES.md` first, in full, since this round leans directly on `commands.py`'s existing parse/dispatch/formatter split rather than building a parallel system. Keep updating the notes as you go, per the working agreement.

This is deliberately scoped to reminders alone — the settings panel and dashboard both depend on this existing first (settings needs reminder config to include from day one; the dashboard needs real reminders to display), so build this fully before either of those rounds starts.

---

## 1. Pure logic — `reminders.py`

Same discipline as every other pure module: no Qt, no file I/O in the core logic (persistence is separate, see Part 2).

- A small `Reminder` structure: `id`, `message`, `due_at` (timestamp), `created_at`.
- `parse_duration(text: str) -> tuple[float | None, str]`: the first whitespace-separated token must match a number immediately followed by `s`, `m`, or `h` (e.g. `10s`, `5m`, `2h` — no spaces within the token, no other units for now). Returns `(seconds, remaining_text)` on a match, `(None, text)` otherwise. This is the same "pure parsing returns a tuple" shape `commands.py`'s `parse_command` already established — follow it, don't invent a different convention.
- `due_reminders(reminders: list[Reminder], now: float) -> list[Reminder]`: which ones have `due_at <= now`.
- Formatter functions matching `commands.py`'s existing `format_*` split (pure, take plain values, return display text): a reply for successfully setting one, a listing for the `reminders` command, a confirmation for `cancel`, and usage-hint text for malformed input (missing duration, missing message, or an unknown id to cancel) — mirroring the existing "never silently do nothing, always reply with something" rule this codebase already holds for unrecognized commands and for `rename` with no argument.

## 2. Persistence

New file `~/.gitten/reminders.json` (same directory as the existing distraction/telegram config files), a plain list of reminders. Load on startup; save whenever the list changes (set or cancel). No artificial cap on how far out a reminder can be scheduled — keep this simple for v1.10.

## 3. New commands (extend the existing dispatch table, don't parallel it)

Add to the same command table `_dispatch_command` already holds, following the exact pattern already established for `streak`/`commits`/`chase` (thin glue in the dispatch method, real logic in the pure module):

| Command | Behavior |
|---|---|
| `remind <duration> <message>` | e.g. `remind 10m take a break`. Schedule it; reply confirming what was set and when. |
| `reminders` | List pending reminders with their id and remaining time. |
| `cancel <id>` | Cancel a pending reminder by the id shown in `reminders`. |

Update `help`'s text (`COMMANDS_HELP_TEXT`) to include these three, the same way it already lists every other command.

## 4. Firing — reuse the existing tick, and handle the away case deliberately

Check `due_reminders` on the same periodic tick already driving the badge/streak/idle checks — no new timer.

**This is the one place suppression logic should go the opposite direction from v1.8's pattern, and it's worth being explicit about why**: v1.8 suppressed one-liners, curiosity, and mouse-chase while `AWAY`, because those are ambient personality touches nobody benefits from seeing alone. A reminder is different — the user explicitly asked for it at a specific time, so it must never be silently dropped just because they stepped away. Two cases:
- **Due while present**: show it immediately via the existing nudge bubble mechanism, same as every other command reply.
- **Due while `AWAY`**: don't fire it into an empty room and let it auto-fade unseen. Hold it, and flush any reminders that became due during the absence at the exact same *away → active* transition point `_check_idle` already uses for the v1.8 welcome-back message — that's an existing, proven hook for "the user just came back," reuse it rather than adding a second one.

## Testing

Unit tests for `parse_duration` (each unit, missing unit, non-numeric, empty string), `due_reminders` (none due, some due, exact-boundary `due_at == now`), and every formatter (including the malformed-input usage-hint cases). Test the dispatch wiring the same way v1.9's Part 2 was verified — a real `GittenApp` against a real scratch setup, not a mock — for `remind`/`reminders`/`cancel`, including the malformed cases (`remind` with no duration, `remind 10m` with no message, `cancel` with a bad id). Live-verify the away-hold-and-flush behavior specifically (simulate a reminder becoming due while `AWAY`, confirm it does *not* fire into the nudge bubble at that moment, then simulate the away→active transition and confirm it fires then) — this is the one genuinely new piece of timing logic this round adds, so it deserves the same live-verification standard the rest of this codebase already holds itself to, not just unit-tested in isolation.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_10_SPEC.md`. Prompt (English): "Read GITTEN_V1_10_SPEC.md and DEVELOPMENT_NOTES.md in full. Build reminders.py, wire the three new commands into the existing dispatch table, and handle the away-hold-and-flush firing behavior exactly as specced — that part is a deliberate exception to v1.8's suppression pattern, don't apply is_away suppression to reminders the way it was applied to one-liners/curiosity/chase. Test live for the away/flush timing specifically. Update DEVELOPMENT_NOTES.md and push when done."
