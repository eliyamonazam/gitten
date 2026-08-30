# Gitten v1.2 — notification inbox & cat personality (feature addendum)

This extends `GITTEN_SPEC.md` and `GITTEN_V1_1_SPEC.md`. Read `DEVELOPMENT_NOTES.md` first for the current architecture (`mood.py`, `status_badge.py`, `distraction.py`, `sprite.py`, `window.py`, `main.py`) — this document only describes what's new. Don't rebuild anything working; extend it, and keep updating `DEVELOPMENT_NOTES.md` as you go (per the working agreement already recorded in that file).

## Feature A: Notification inbox

Clicking the cat (while it's in its normal front-facing state — see the interaction rule below) switches the window into a scrollable notification list view instead of the kitten sprite: app name, short text, and time for each current Windows notification. A small back arrow (top-left of the list) returns to the normal kitten view. Keep this inside the existing single frameless/topmost/draggable widget — don't spawn a second window; toggle what's drawn/laid out based on a `view_mode` (`"pet"` / `"inbox"`) flag, e.g. via a `QStackedWidget` inside the current widget.

**Data source**: `Windows.UI.Notifications.Management.UserNotificationListener` (WinRT), via the official Microsoft WinRT-for-Python projection packages (`winrt-Windows.UI.Notifications.Management` and its dependencies). Flow:
1. `UserNotificationListener.Current` → `await RequestAccessAsync()` — this is what triggers the one-time Windows permission prompt (Settings → Privacy → Notifications). If access is denied or not yet granted, don't crash: the inbox view should show a short friendly message instead ("Notification access not granted yet") rather than an empty/broken list.
2. Once access is granted: `await GetNotificationsAsync(NotificationKinds.Toast)` for the current snapshot when the inbox is opened. Subscribing to the `NotificationChanged` event for live updates is a nice-to-have, not required for v1.2 — a fresh fetch each time the inbox is opened is an acceptable simplification.

New module `notifications.py`: keep the WinRT async calls thin and isolated here (same "thin I/O wrapper" spirit as `system_monitor.py` / `foreground_window.py`), and keep whatever formatting logic decides what text to show per-item in a small separate, plain-Python, unit-testable function — don't mix WinRT specifics into anything that doesn't need to touch WinRT directly.

**If the `winrt` packages turn out to be unavailable or unstable to install/run in your environment**: don't force it. Degrade gracefully — log the failure and make the inbox view show "notifications unavailable" — rather than blocking the rest of v1.2 (Feature B does not depend on this one at all).

## Feature B: Sulking & reconciliation (a third independent state layer)

New pure module `attention.py`, following the exact same discipline as `mood.py` / `status_badge.py` / `distraction.py`: no Qt imports, all timestamps passed in by the caller, fully unit-testable without a running app.

- Tracks `last_interaction_at`. Any click or drag on the cat, in any state, resets this timestamp.
- If `now - last_interaction_at >= 30 minutes` and it isn't already mid-reconciliation, the cat enters `SULKING` (turned away).
- While `SULKING`, each distinct **click that isn't part of a drag** (a "pet") increments `pets_received` by 1 — a plain click-and-release in place, not a click-and-move.
- `turn_stage(pets_received)` → 5 discrete stages, not a smooth rotation:
  - 0 pets: fully turned away
  - 1 / 2 / 3 pets: progressively more turned toward the viewer ("glancing over shoulder")
  - 4 pets: fully reconciled — resumes normal front-facing rendering (mood/badges as usual), and `pets_received` resets to 0
- Deliberate v1.2 simplification: no decay if the user stops petting partway through a reconciliation — it just waits at that partial stage until they resume. Fine to revisit later if it feels wrong in practice; don't over-engineer this now.

**Interaction rule (resolves the click ambiguity with Feature A)**: a plain click on the cat opens the notification inbox (Feature A) ONLY when `view_mode == "pet"` AND the attention state is NOT `SULKING`. While `SULKING`, the same click is instead routed to `attention.py` as a pet. This is intentional personality, not just a technical workaround — the cat won't show you anything while it's mad at you.

**Sprite work** (`sprite.py`, additive — same optional-parameter pattern used for v1.1's badges/nudge, existing call sites keep working unchanged): 5 discrete back-view poses matching the stages above, same proportions/style as the existing front view so it reads as the same character rather than a different drawing.

## Explicitly deferred (not this round)

Everything beyond these two features — including the mouse-chase idea you mentioned. You said you have a lot more ideas for this project: next time, send the **whole list** at once (even rough one-liners are fine) rather than one at a time, so they can be triaged and batched properly instead of bolted on mid-build. That's how v1 and v1.1 stayed clean.

## How to hand this to Claude Code
Put this file alongside the existing specs as `GITTEN_V1_2_SPEC.md`. Prompt (in English, for terminal compatibility): "Read GITTEN_V1_2_SPEC.md — it extends the existing app. Implement both features. If the WinRT notification packages are unavailable, degrade Feature A gracefully rather than blocking Feature B. Keep updating DEVELOPMENT_NOTES.md as you go, per the working agreement already recorded there."
