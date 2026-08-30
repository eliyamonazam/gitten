"""Thin WinRT wrapper around Windows' notification listener, plus a small
pure formatting helper.

The WinRT calls themselves are kept isolated here -- same "thin I/O
boundary" spirit as `system_monitor.py` / `foreground_window.py` -- so
nothing else in the app needs to know WinRT specifics. Every function that
touches WinRT degrades to returning `None`/`False` on failure rather than
raising: per the v1.2 spec, if these packages are unavailable or unstable,
the inbox view should just say so rather than blocking the rest of the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

try:
    from winrt.windows.ui.notifications import NotificationKinds
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener,
        UserNotificationListenerAccessStatus,
    )

    _WINRT_AVAILABLE = True
except ImportError:
    _WINRT_AVAILABLE = False


@dataclass(frozen=True)
class NotificationItem:
    """One formatted row for the inbox view."""

    app_name: str
    text: str
    time_text: str


def format_notification(
    app_name: str | None,
    text_lines: list[str],
    created_at: datetime,
    now: datetime,
) -> NotificationItem:
    """Pure formatting: decide what one inbox row should say.

    `text_lines` are a toast's text elements top to bottom (title first),
    joined into one short line. `time_text` is a small relative stamp ("just
    now", "14m ago", "3h ago", or a plain date once it's more than a day
    old). No Qt or WinRT involved, so this is trivially testable with plain
    datetimes.
    """
    text = " -- ".join(line for line in text_lines if line) or "(no text)"

    seconds = (now - created_at).total_seconds()
    if seconds < 60:
        time_text = "just now"
    elif seconds < 3600:
        time_text = f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        time_text = f"{int(seconds // 3600)}h ago"
    else:
        time_text = created_at.astimezone().strftime("%b %d")

    return NotificationItem(app_name=app_name or "Unknown app", text=text, time_text=time_text)


def is_supported() -> bool:
    """Whether the WinRT notification packages imported successfully."""
    return _WINRT_AVAILABLE


async def request_access() -> bool:
    """Trigger (if needed) the one-time Windows notification-access prompt.

    Returns True once access is confirmed granted, False on denial or any
    failure -- including the WinRT packages not being installed at all.
    """
    if not _WINRT_AVAILABLE:
        return False
    try:
        listener = UserNotificationListener.current
        status = await listener.request_access_async()
        return status == UserNotificationListenerAccessStatus.ALLOWED
    except Exception:
        return False


async def fetch_notifications() -> list[NotificationItem] | None:
    """Current snapshot of toast notifications, newest first.

    Returns None if WinRT is unavailable, access isn't granted, or the call
    fails for any reason -- the caller shows an "unavailable" message rather
    than an empty/broken list in that case. A fresh fetch on every open is
    an acceptable v1.2 simplification (no live NotificationChanged
    subscription yet).
    """
    if not _WINRT_AVAILABLE:
        return None
    try:
        listener = UserNotificationListener.current
        if listener.get_access_status() != UserNotificationListenerAccessStatus.ALLOWED:
            return None
        notifications = await listener.get_notifications_async(NotificationKinds.TOAST)
    except Exception:
        return None

    now = datetime.now(timezone.utc)
    items = []
    for i in range(notifications.size):
        try:
            n = notifications[i]
            app_name = n.app_info.display_info.display_name
            lines = [el.text for el in n.notification.visual.bindings[0].get_text_elements()]
            items.append(format_notification(app_name, lines, n.creation_time, now))
        except Exception:
            continue
    items.reverse()  # the listener returns oldest-first
    return items
