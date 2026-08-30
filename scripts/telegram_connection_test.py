"""Standalone script: test the Telegram ("userbot") connection in isolation.

Per the v1.3 spec, this is deliberately built and verified on its own,
outside the app, before any of it touches ``main.py``. It logs in with your
own Telegram account (not a bot) using Telethon and prints the sender and
text of every incoming message, so the connection itself can be proven
solid before wiring reactions into the kitten.

Run it directly from the project's venv:

    python scripts/telegram_connection_test.py

First run prompts for your api_id/api_hash (from https://my.telegram.org/apps),
then your phone number, then the login code Telegram sends you. All of that
-- and the resulting login session -- is cached under ``~/.gitten/``, never
inside this project folder. The session file
(``~/.gitten/telegram.session``) is equivalent to a password: this script
never logs or prints its contents, and .gitignore excludes any ``.gitten/``
that might ever end up inside the repo by mistake.

Press Ctrl+C to stop.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running this script directly from a checkout without installing the
# package first (`python scripts/telegram_connection_test.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from telethon import TelegramClient, events  # noqa: E402

from gitten.telegram_config import (  # noqa: E402
    DEFAULT_SESSION_PATH,
    GITTEN_DIR,
    load_config,
    save_config,
)


def prompt_for_credentials() -> dict:
    print("No cached Telegram API credentials found.")
    print("Get an api_id / api_hash at https://my.telegram.org/apps")
    api_id = int(input("api_id: ").strip())
    api_hash = input("api_hash: ").strip()
    save_config(api_id, api_hash)
    print(f"Saved to {GITTEN_DIR / 'telegram_config.json'}")
    return {"api_id": api_id, "api_hash": api_hash}


def _sender_label(sender) -> str:
    if sender is None:
        return "<unknown sender>"
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    return f"id:{getattr(sender, 'id', '?')}"


async def run() -> None:
    config = load_config() or prompt_for_credentials()

    client = TelegramClient(str(DEFAULT_SESSION_PATH), config["api_id"], config["api_hash"])

    @client.on(events.NewMessage(incoming=True))
    async def _on_message(event) -> None:
        sender = await event.get_sender()
        print(f"[{_sender_label(sender)}] {event.raw_text}")

    await client.start()
    me = await client.get_me()
    print(f"Connected as {_sender_label(me)}. Listening for messages -- Ctrl+C to stop.")
    await client.run_until_disconnected()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
