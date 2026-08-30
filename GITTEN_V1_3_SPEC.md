# Gitten v1.3 — Telegram integration (feature addendum)

This extends everything built so far — read `DEVELOPMENT_NOTES.md` for the current architecture before starting. Keep updating that file as you go, per the working agreement already recorded there.

## Overview

Gitten connects to the user's own Telegram account (not a bot — a personal "userbot" connection) and reacts differently depending on who sends a message:
- A sender on the **favorites** list → the cat does an excited "grab" animation near the mouse cursor, then runs across the screen to the Telegram taskbar icon and sits there, flashing the icon to draw attention.
- A sender on the **bad** list → the cat runs to the same taskbar-icon spot but with an annoyed/hissing animation instead, and a small warning badge, also flashing the icon.
- Everyone else → no reaction at all.

**Build and test the Telegram connection in isolation first**, as a small standalone script that just logs in and prints incoming messages with the sender's username, before wiring it into the main app. This is a new category of integration (networked, credentialed) compared to everything built so far — de-risk it on its own before touching `main.py`.

## Security — read this before writing any code

- **Never commit any Telegram credential to git.** The login session file and the `api_id`/`api_hash` must live outside the project folder, in `~/.gitten/` (the same directory already used for the distraction-list config), which is not part of the repository. Double-check `.gitignore` still correctly excludes anything under a local `.gitten/` if it's ever created inside the project folder by mistake.
- The resulting Telegram session file is equivalent to a password — anyone with it can log in as the user. Treat it accordingly; don't log its contents, don't print it, don't include it in any error message.

## 1. Connection setup

New module `telegram_watcher.py`, using **Telethon**.

- Add a new tray menu entry, "Connect Telegram...", which runs an interactive first-time login: prompts for `api_id` / `api_hash` (simple Qt input dialogs, only asked once and then cached in `~/.gitten/telegram_config.json`), then phone number, then the login code Telegram sends. On success, Telethon saves its own session file to `~/.gitten/telegram.session` — point Telethon's `session` parameter at that path explicitly rather than letting it default into the project folder.
- If no session/config exists yet, Telegram features are simply inactive (no crash, no nagging) — the app works exactly as it does today until the user explicitly connects.

## 2. Contact lists

New file `~/.gitten/telegram_lists.json`: `{"favorites": [...], "bad": [...]}`, storing Telegram usernames or numeric user IDs. Same "JSON file the user can hand-edit" pattern as the distraction list from v1.1 — no settings UI needed yet.

Add a small pure, testable function (e.g. in `telegram_watcher.py` or a shared `contacts.py`) that takes a sender identifier and the two lists and returns `"favorite"`, `"bad"`, or `None` — keep this list-matching logic separate from the Telethon event-handling code so it's unit-testable without a live connection.

## 3. Listening for messages

Run the Telethon client's `asyncio` event loop in its own background thread (same architectural pattern as `git_watcher.py`'s `watchdog` thread) rather than introducing a new async-integration approach like `qasync`. Register a Telethon `NewMessage` event handler; on each incoming message, look up the sender against the contact lists and, if it's a match, emit a Qt signal (`favorite_message` or `bad_message`) back to the main thread — the same cross-thread signal pattern already used for `commit_detected` / `dirty_changed`.

## 4. The reaction sequence

New animation state in `window.py` (self-clearing on a timer, same pattern as the v1.1 nudge): `start_telegram_alert(category)` where `category` is `"favorite"` or `"bad"`.

- **Locate the Telegram taskbar icon**: try UI Automation (`pywinauto`, targeting the taskbar's `Shell_TrayWnd`) to find the button whose accessible name matches "Telegram". If that fails or is unreliable (this is known to be flakier on Windows 11 than Windows 10 — don't sink excessive time into making it perfect), fall back to a fixed approximate position near the bottom-right of the screen, close to the system tray. Exact pixel precision isn't required — "ran over to roughly where Telegram lives" reads fine.
- **Favorite**: play a quick "grab" animation at the cat's current position (paws reaching out, near wherever the mouse cursor happens to be — don't move the actual OS cursor), then animate the cat moving/running across the screen to the located taskbar spot, then a happy sitting pose once there.
- **Bad**: same run-over motion, but an annoyed/hissing animation instead of the happy grab, plus a small warning badge rendered near the cat while it sits there (reuse the badge-rendering approach from `status_badge.py`'s icons if convenient, doesn't need to be the same module).
- Once arrived, call `FlashWindowEx` on the Telegram window to flash its taskbar entry (standard, permission-free way to draw attention — do **not** attempt to force the window to the foreground; Windows blocks background processes from stealing focus and this will likely silently fail or behave inconsistently).
- After arriving, the cat stays at the taskbar spot until either: the user clicks it (returns immediately to its normal position/state), or ~30 seconds pass with no interaction (auto-returns). Reuse the existing click-handling on the cat for the "dismiss" case; this is a good moment to double check it doesn't collide with the existing petting/notification-inbox click rules from v1.2 — while showing a Telegram alert, a click should simply dismiss the alert and return to normal, taking priority over the pet/inbox rules.

## Explicitly deferred (not this round)

Everything else — the mouse-chase idea and anything else still on your wishlist. This round is Telegram-only; get it solid before adding more.

## How to hand this to Claude Code

Put this file alongside the existing specs as `GITTEN_V1_3_SPEC.md`. Prompt (English, for terminal compatibility): "Read GITTEN_V1_3_SPEC.md. Start by building and testing the Telegram connection as a small standalone script per the spec, before touching main.py. Never write any Telegram credential inside the project folder. Keep updating DEVELOPMENT_NOTES.md as you go."
