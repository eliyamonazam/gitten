# Gitten — Development Notes

This document explains what was built, how it works, the decisions behind
it, and the debugging story from this build session — a full record for
future reference.

## 1. Starting point

The only input was `GITTEN_SPEC.md`, describing a Windows desktop pet: a
kitten that watches a git repository and changes mood (idle / happy /
waiting) based on git activity. The spec fixed the tech stack (Python
3.11+, PySide6, watchdog, pytest, PyInstaller), the project layout, and
exact colors/shapes for the sprite. The task was to build the v1 MVP
exactly as scoped, with as polished a UI as the "no external art assets,
QPainter primitives only" constraint allows.

## 2. What was built

### Project layout (matches the spec's suggested structure)

```
gitten/
├── src/gitten/
│   ├── __init__.py
│   ├── main.py            # entry point: QApplication, tray, window, wiring
│   ├── window.py           # transparent always-on-top draggable QWidget
│   ├── sprite.py           # QPainter drawing code for the kitten
│   ├── mood.py             # pure state machine, no Qt imports
│   └── git_watcher.py       # watchdog-based watcher
├── tests/
│   └── test_mood.py
├── assets/
│   └── preview.png          # rendered 3-mood preview used in the README
├── .github/workflows/ci.yml
├── pyproject.toml
├── build_exe.bat
├── README.md
├── LICENSE
└── DEVELOPMENT_NOTES.md      # this file
```

### `mood.py` — the state machine

This is the one piece of logic that actually needed correctness
guarantees, so it was written with **zero Qt imports** and driven entirely
by timestamps passed in by the caller (`now: float`), never by reading the
system clock itself. That's what makes it trivially unit-testable — tests
pass in fake, arbitrary increasing numbers instead of sleeping in real
time.

Three inputs drive it:
- `on_commit(now)` — a commit was observed; starts a `happy_seconds`
  countdown (default 4s) and clears any "dirty" streak.
- `update_dirty(is_dirty, now)` — the result of a `git status --porcelain`
  check. The first moment `is_dirty` flips to `True`, a `dirty_since`
  timestamp is recorded.
- `tick(now)` — periodic re-evaluation: expires the happy celebration once
  its window passes, and promotes `IDLE → WAITING` once
  `now - dirty_since >= waiting_threshold_seconds` (default 30 minutes).

9 unit tests in `tests/test_mood.py` cover: default idle state, commit →
happy, happy expiring back to idle, dirty changes under/over the waiting
threshold, cleaning up resetting to idle, a commit resetting an in-progress
waiting streak, a fresh dirty streak starting after a happy expiry, and
committing again while already happy extending the celebration. All 9
pass.

### `git_watcher.py` — event-driven git detection

Per the spec, this does **not** poll `git status` on a timer. Instead it
uses `watchdog` to watch the `.git/` directory non-recursively for two
specific files:
- `COMMIT_EDITMSG` — touched on every `git commit` → emits `commit_detected`
- `index` — touched on `git add` / staging changes → triggers a debounced
  `git status --porcelain` check (0.3s debounce, since git can touch the
  index file several times during one operation)

`_run_git_status()` shells out via `subprocess.run` with a 5s timeout and
returns `True`/`False`/`None` (None = couldn't determine, e.g. repo
deleted mid-run — signal is dropped rather than crashing anything).

`GitWatcher` is a `QObject` with two Qt signals (`commit_detected`,
`dirty_changed(bool)`) so the watchdog thread can safely hand events back
to the Qt main thread via Qt's built-in cross-thread signal queuing — no
manual locking needed.

### `sprite.py` — the actual kitten art

Everything is hand-drawn with `QPainter` primitives in a fixed 128×128
logical coordinate space (`paint_kitten(painter, rect, mood, t)` scales
that into whatever rect it's given) — no bitmap assets, per the spec.
Beyond the spec's baseline description, this went further on animation
polish since "best possible UI" was the ask:

- **Body**: an ellipse with a radial gradient (light highlight → base
  coral `#E8935F`) instead of flat fill, for a glossier, less flat look.
- **Breathing**: a subtle continuous sine-wave vertical squish/stretch on
  the whole body + ears, plus a small vertical bob — so the kitten never
  looks like a static sticker even at rest.
- **Tail**: a cubic Bézier path that sways side to side using two summed
  sine waves at different frequencies, so the motion doesn't look
  mechanically periodic.
- **Ground shadow**: a soft translucent ellipse under the body for visual
  grounding.
- **Idle**: closed-eye curves, a small mouth, and "zzz" letters that
  continuously drift upward and fade out on a loop (each letter offset in
  phase and growing in size, mimicking a typical sleep-indicator
  animation).
- **Happy**: upward eye curves, an open smile, a pulsing heart (scale
  breathing via `sin`) above the head, plus three small gold sparkles that
  drift upward and fade, gently staggered.
- **Waiting**: white circular eyes with pupils that drift left/right on a
  slow sine (a "nervous glancing around" effect), angled eyebrows, a wavy
  worried mouth, a bouncing speech bubble with "!", and a very small
  high-frequency horizontal jitter on the whole body (a "nervous shiver").

A rendered 3-mood contact sheet was generated (`assets/preview.png`, shown
in the README) by calling `paint_kitten` directly onto an off-screen
`QPixmap` — this is also how the tray icon is generated at runtime
(`_make_icon` in `main.py`), so the tray icon always matches the widget's
current mood.

### `window.py` — the transparent always-on-top widget

- `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
  Qt.WindowDoesNotAcceptFocus` + `Qt.WA_TranslucentBackground` +
  `Qt.WA_ShowWithoutActivating` — frameless, transparent, floats above
  everything, never steals keyboard focus from whatever you're typing in
  (important for a desktop pet that sits there while you work), and
  doesn't show up in the taskbar/alt-tab (`Qt.Tool`).
- A `QTimer` repaints at ~30 fps so the idle animations (breathing, tail
  sway, zzz drift, sparkles) run continuously regardless of mood changes.
- Mouse events implement drag-to-move; a `moved` Qt signal fires on every
  move so `main.py` can persist the position via `QSettings` without the
  window needing to know anything about settings itself.
- `default_position()` anchors it near the bottom-right of the primary
  screen's *available* geometry (i.e. excluding the taskbar), so it reads
  as "sitting on the taskbar" on first run.

### `main.py` — wiring

Builds the `QApplication`, `QSystemTrayIcon` (with a "Choose watched
repo..." action using `QFileDialog.getExistingDirectory`, and "Quit"),
creates the `GitWatcher` and `KittenWindow`, and connects everything:

- `watcher.commit_detected` → `mood_machine.on_commit(now)` → repaint +
  update tray icon
- `watcher.dirty_changed` → `mood_machine.update_dirty(is_dirty, now)` →
  same
- A 5-second `QTimer` calls `mood_machine.tick(now)` so the happy timeout
  and waiting threshold get re-evaluated even if no new git event arrives
  in between.

`QSettings("Gitten", "Gitten")` (which on Windows lives in
`HKEY_CURRENT_USER\Software\Gitten\Gitten`) persists the watched repo path
and window position across restarts. On first launch with nothing saved,
it prompts for a repo folder.

## 3. Testing performed this session

- `pytest -q` → **9/9 passed** (the mood state machine).
- Manually created a scratch git repo and pointed a running instance at it
  (via pre-seeding `QSettings`) to exercise the watcher end-to-end.
- Rendered each mood (`IDLE`, `HAPPY`, `WAITING`) directly to PNG via an
  off-screen `QPixmap` + `paint_kitten(...)` call, and visually inspected
  each — this is what produced `assets/preview.png` and confirmed the art
  actually looks like the spec's description (closed eyes + zzz; happy
  eyes + heart + sparkles; wide eyes + eyebrows + "!" bubble).

## 4. A debugging detour worth recording

While trying to screenshot the *live running window* on the real desktop
(to double check window placement, not just the sprite art), the
automated screenshots kept showing the kitten in inconsistent, wrong
positions — nowhere near the computed bottom-right anchor. Chasing that
down:

1. First suspicion: a Windows DPI-scaling mismatch between Qt's logical
   coordinate space and the physical screen. Ruled out with a minimal
   reproduction script — a bare `QWidget` moved to the same computed
   coordinates landed exactly where expected.
2. Actual cause: launching the app via this session's background-bash
   tooling on Windows/Git-Bash spawns **two** `python.exe` processes (a
   parent + a child, an artifact of how MSYS emulates `fork`/background
   jobs on Windows). Only the child ever hosts real GUI windows, but
   several of these got launched across repeated test iterations and
   **weren't fully killed each time** — leftover instances kept running
   in the background, each with the same `QSettings`-backed window
   position key, each writing its own position to the shared Windows
   registry key on exit. That produced the "position keeps changing to
   something unexplained" symptom: it wasn't the app's positioning logic,
   it was multiple zombie instances fighting over one shared settings
   key.
3. Fix applied *to the debugging process*, not the code: killed all
   stray `python.exe` processes, cleared the stale
   `HKCU\Software\Gitten\Gitten\window` registry value, and relaunched a
   single clean instance — which landed exactly at the computed
   `(1857, 977)` bottom-right position, confirming the app's own logic
   was correct all along.
4. Separately, a raw `CopyFromScreen` screenshot of that exact window
   region came back showing unrelated desktop content instead of the
   kitten, even with only one confirmed instance running and correct
   window styles (`WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW`
   verified via `GetWindowLong`). This looks like a quirk of taking GDI
   screenshots of a layered/topmost window in this particular sandboxed
   session rather than an app bug, so live-desktop screenshot
   verification was abandoned in favor of the direct off-screen
   `QPixmap` rendering described above, which conclusively verified the
   art.

**Net effect on the actual code**: none of this changed a single line of
the shipped source — it was purely a test-environment artifact. It's
recorded here so that if window-position weirdness ever gets reported
against the real app, "check for leftover zombie processes fighting over
the same `QSettings` key" is the first thing to check before assuming a
logic bug.

## 5. How to run / build / test (quick reference)

```bash
# Run from source
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m gitten.main

# Run tests
pip install -e .[dev]
pytest

# Build the portable .exe (Windows only)
build_exe.bat   # → dist\Gitten.exe
```

## 6. Explicitly not built (per spec's out-of-scope list for v1)

- Multiple kittens at once
- Reacting to GitHub Actions / CI status
- Unlockable skins/fur colors
- Sound effects
- Cross-platform support (Windows-only for now)

## 7. v1.1 — system awareness & social nudge

Input was `GITTEN_V1_1_SPEC.md`, which extends v1 with three features:
system status badges, a distraction nudge, and a right-click stats menu.
The spec was explicit that `mood.py`'s existing behavior must not change —
it wasn't touched (only read); everything new is additive.

### New files

```
src/gitten/
├── status_badge.py       # pure logic: which badge to show, no Qt imports
├── distraction.py        # pure logic: title/process matching + streak timer, no Qt/win32
├── system_monitor.py     # thin psutil wrapper (the only file that touches psutil)
└── foreground_window.py  # thin win32gui/win32process wrapper (the only file that touches win32)
tests/
├── test_status_badge.py  # 14 tests
└── test_distraction.py   # 13 tests
```

### `status_badge.py` — the status-badge state machine

Written with the exact same discipline as `mood.py`: zero Qt imports, all
inputs (`battery_percent`, `plugged_in`, `cpu_percent`, `mem_percent`,
`disk_percent`) passed into `StatusBadgeTracker.update(...)` by the caller
rather than read internally, so it's trivially unit-testable. This is a
**separate signal from mood, by design** — the spec calls out that the cat
can be `happy` (just committed, driven by `mood.py`) and show a low-battery
badge at the same time, so the two state machines must stay independent
rather than merged into one.

CPU/mem are smoothed over a rolling `deque(maxlen=10)` average so a single
spike doesn't trip the "high resource usage" badge — only sustained load
does. Priority when several conditions are true at once (highest first):
critical battery → low disk → high resource → charging → low battery,
implemented as a tuple scanned in order rather than a chain of `elif`s, so
the ordering itself is the single source of truth. `Badge.NONE` (no icon
at all) is the common case, matching the spec's "must not feel naggy."

### `distraction.py` — nudge streak + list matching

Also zero Qt/win32 imports. Two independent pieces:
- `is_distracting_window(process_name, title, titles, processes)` —
  case-insensitive substring match on title, exact case-insensitive match
  on process name, exactly as specced.
- `DistractionTracker` — same timestamp-injection pattern as
  `MoodMachine`: `update(is_distracting, now)` tracks a continuous streak
  and returns `True` the instant a nudge should fire. Fires once at the
  20-minute threshold, then again every additional 20 minutes while the
  streak stays unbroken (tracked via a `_next_fire_elapsed` watermark that
  increments by the threshold each time it fires, rather than a simple
  "time since last nudge" check, so a long binge nudges on a steady
  cadence instead of drifting). The instant the foreground window stops
  matching, the streak and the watermark both reset.

`load_distraction_lists(path)` reads a user-editable JSON file
(`~/.gitten/distraction_config.json`, e.g.
`{"titles": [...], "processes": [...]}`) and falls back to the shipped
defaults (`instagram`/`twitter`/`x.com`/`tiktok`/`reddit`/`youtube` titles,
`telegram.exe`/`discord.exe` processes) if the file is missing or invalid
— a JSON file was chosen over a settings UI per the spec's "a JSON file or
QSettings-backed list is enough for v1.1."

### `system_monitor.py` / `foreground_window.py` — the only I/O boundaries

Both are deliberately thin and dumb: `sample_system()` just calls
`psutil.sensors_battery()` / `cpu_percent()` / `virtual_memory()` /
`disk_usage()` and returns a `SystemSample` dataclass; `psutil.cpu_percent`
uses `interval=None` (non-blocking, compares against the last call) since
it's polled on a recurring timer rather than a one-shot. `disk_usage`
targets `os.environ["SystemDrive"]` so it checks whatever drive Windows is
actually installed on, not a hardcoded `C:\`.
`get_foreground_window()` wraps `win32gui.GetForegroundWindow()` +
`win32process.GetWindowThreadProcessId()` + `psutil.Process(pid).name()`,
returns `None` on any failure (no window focused, access denied, or
non-Windows) rather than raising, and is guarded by a top-level
`try/except ImportError` so importing this module doesn't hard-crash on a
platform without `pywin32`.

### `sprite.py` — additive rendering only

`paint_kitten()` gained three new **optional, defaulted** parameters
(`badge=None`, `nudge_text=None`, `nudge_opacity=0.0`) so every existing
call site (the tray icon generator, the old test renders) keeps working
unchanged. Badges render as a small icon at a fixed offset top-left of the
head (`_BADGE_POS_OFFSET`, deliberately on the opposite side from the
mood overlay which lives top-center/right, so the two never collide
visually): a pulsing red/orange battery outline for critical/low battery
(pulse speed differs — fast vs slow, per spec), a small yellow lightning
bolt for charging, a bobbing blue teardrop for high resource use, and a
grey disk-with-hole plus a small orange warning triangle for low disk.
The nudge draws a small paw circle that swings up on a sine wave beside
the body (the "wave" animation) plus a rounded speech-bubble with a tail,
rendered with `painter.setOpacity(nudge_opacity)` so the caller controls
fade purely by varying that one float.

### `window.py` — nudge lifecycle lives here, not in `sprite.py`

`sprite.py` stays pure rendering (given an opacity, draw it); the actual
"how does opacity change over time" timeline lives in `KittenWindow`:
`show_nudge(text)` just records the text and a start timestamp;
`_nudge_opacity(now)` (called every paint, since the window already
repaints continuously at ~30fps for the breathing/tail animation) computes
full opacity for the first 3 of the 4 total seconds, then linearly fades
over the last 1 second, and self-clears the nudge state once the 4 seconds
are up — so nothing external needs to "remember" to turn the nudge off.

### `main.py` — wiring

Three new pieces layered onto the existing structure without touching the
mood-related wiring:
- A `StatusBadgeTracker` fed by a new 7-second `QTimer` (`_on_system_tick`)
  calling `sample_system()` → `window.set_badge(badge)`.
- A `DistractionTracker` + the loaded title/process lists, fed by a new
  3-second `QTimer` (`_on_distraction_tick`) calling
  `get_foreground_window()` → `is_distracting_window(...)` →
  `tracker.update(...)` → `window.show_nudge(NUDGE_MESSAGE)` when it
  returns `True`. `NUDGE_MESSAGE` is the Persian line from the spec
  ("یه وقفه کوتاه چطوره؟").
- `_show_context_menu` (previously just popped the tray's own menu) now
  builds a **separate** `QMenu` from scratch on every right-click —
  recomputing rather than caching, so it's always current: commits today
  via a new `count_commits_today(repo_path)` helper added to
  `git_watcher.py` (same subprocess pattern as `_run_git_status`, using
  `git log --since=midnight --oneline`), current battery %, the watched
  repo path, and session uptime (`_format_uptime()`, tracked from a
  `time.monotonic()` timestamp captured at app construction). "Change
  watched repo" and "Quit" entries are duplicated here per the spec
  ("alongside, not instead of, the tray icon's existing versions") — the
  tray's own menu (`_build_tray`) was left completely untouched.

### New dependency setup

Added `psutil>=5.9` and `pywin32>=306; sys_platform == 'win32'` to
`pyproject.toml`'s `dependencies`, and installed both into the existing
`.venv` (`pip install psutil pywin32`).

## 8. Testing performed this session (v1.1)

- `pytest -q` → **36/36 passed** total (9 pre-existing `test_mood.py` +
  14 new `test_status_badge.py` + 13 new `test_distraction.py`). One test
  bug was caught and fixed during this pass: an early version of
  `test_single_cpu_spike_does_not_trigger_high_resource` used
  `plugged_in=True`, which unintentionally tripped the `CHARGING` badge
  before the CPU-spike assertion even mattered — fixed by using
  `plugged_in=False` for that test since it wasn't testing the charging
  path.
- Rendered every `Badge` value plus the nudge state directly to an
  off-screen `QPixmap` via `paint_kitten(...)` (headless, `QT_QPA_PLATFORM
  =offscreen`) to confirm the new drawing code paths don't throw and
  produce a paint.
- Instantiated the full `GittenApp` headlessly and manually invoked
  `_on_tick`, `_on_system_tick`, and `_on_distraction_tick` once each to
  confirm the new timers' handlers are wired correctly end-to-end (real
  `psutil` and `win32gui` calls, not mocked) without exceptions.
- Did **not** verify the nudge/badges visually on a live running window
  this session (no interactive desktop session available) — that's the
  one thing worth double-checking by eye before considering v1.1 fully
  verified, the same way `assets/preview.png` was produced for v1's three
  moods.

## 9. v1.2 — notification inbox & cat personality

Input is `GITTEN_V1_2_SPEC.md`. This had never actually been built despite
being numbered before v1.3 — the previous session went straight from v1.1
to the v1.3 Telegram script, and this session went back to fill in the gap
before continuing v1.3, per this session's explicit instructions. Both of
the spec's features are now implemented and wired into `main.py`.

### Feature A: notification inbox

**New module `src/gitten/notifications.py`** — a thin WinRT wrapper (same
"thin I/O boundary" spirit as `system_monitor.py` / `foreground_window.py`)
plus one pure, testable formatting function:

- `is_supported()` / `request_access()` / `fetch_notifications()` wrap
  `Windows.UI.Notifications.Management.UserNotificationListener` behind a
  top-level `try/except ImportError` guard (`_WINRT_AVAILABLE`) and a
  broad `except Exception` around every actual WinRT call, so a missing
  package, a denied permission, or any WinRT-side failure all degrade to a
  `None`/`False` return rather than raising, exactly as the spec asks
  ("don't force it... degrade gracefully").
- `format_notification(app_name, text_lines, created_at, now)` is the pure
  piece the spec calls out separately: given plain strings and datetimes
  (no WinRT objects), it decides the one-line text (joining a toast's text
  elements with " -- ") and a small relative time stamp ("just now",
  "14m ago", "3h ago", or a plain date past a day). Fully unit-tested
  without touching Windows at all.

**API shape was reverse-engineered against the real, installed package**
rather than guessed, since the winrt-python projection's exact method names
aren't obvious from the spec text alone: `UserNotificationListener.current`
is a property (not `get_current()`); `get_access_status()` /
`request_access_async()` return a `UserNotificationListenerAccessStatus`
(`ALLOWED`/`DENIED`/`UNSPECIFIED`); `get_notifications_async(NotificationKinds.TOAST)`
returns an indexable collection ordered **oldest first** (reversed in
`fetch_notifications()` so the inbox shows newest first); each item exposes
`.app_info.display_info.display_name`, `.creation_time` (a tz-aware
`datetime`), and `.notification.visual.bindings[0].get_text_elements()`
for the title/body text. This was all confirmed against this machine's own
real Windows notifications (see Testing below), not just read from docs.

**A packaging quirk worth recording**: `pip install winrt-Windows.UI.Notifications.Management`
alone was not enough to actually run the code — importing it and calling
into it raised `ModuleNotFoundError` for `winrt.windows.foundation`, then
`winrt.windows.foundation.collections`, then
`winrt.windows.applicationmodel` one at a time, each only surfacing once
the previous one was fixed and the code actually touched that namespace.
The winrt-python packages split every WinRT namespace into its own PyPI
package and don't declare all of these as transitive dependencies of each
other. All five packages actually needed ended up added to
`pyproject.toml` explicitly (`winrt-Windows.UI.Notifications`,
`winrt-Windows.UI.Notifications.Management`, `winrt-Windows.Foundation`,
`winrt-Windows.Foundation.Collections`, `winrt-Windows.ApplicationModel`),
all guarded by `sys_platform == 'win32'` like `pywin32` already is —
anyone reproducing this environment from scratch should expect to hit the
same chain of `ModuleNotFoundError`s if any one of these five is missing,
and the fix each time is "install the specific winrt-* namespace package
the traceback names," not a general WinRT setup problem.

**`window.py`** gained the inbox view itself: a `view_mode` flag
(`"pet"` / `"inbox"`) plus a child `QWidget` panel (a back button, a
`QListWidget`, and a fallback `QLabel` for the two "nothing to show" states)
built once in `_build_inbox_panel()` and shown/hidden rather than spawning
a second window, per the spec. `open_inbox()` / `close_inbox()` grow and
shrink the window via `_resize_anchored_bottom_right()`, which keeps the
window's bottom-right corner fixed across the resize (using `QRect.moveBottomRight`,
not manual arithmetic — an earlier manual-arithmetic version was off by one
pixel because `QRect.bottomRight()` is inclusive; caught by an automated
round-trip check, see Testing) so the inbox grows up-and-left from the same
taskbar-adjacent spot instead of drifting or going off-screen, and closing
it returns to the exact pixel position it had before opening.
`set_inbox_items()` takes either the sentinel strings `INBOX_UNAVAILABLE` /
`INBOX_ACCESS_NOT_GRANTED` (window-owned display copy, since the WinRT
module itself shouldn't know UI text) or a real (possibly empty) list of
`NotificationItem`.

**`main.py`**'s `_fetch_inbox_snapshot()` does one `asyncio.run(...)` call,
synchronously, from the click handler that opens the inbox — a deliberate
simplification: unlike the Telegram feature (which needs a long-lived
background event loop per the v1.3 spec), this is a single WinRT
round-trip triggered by one click, so a brief block on the Qt UI thread was
judged an acceptable trade for not introducing a second threading pattern
into the app. Worth revisiting if it's ever felt as UI jank in practice.

### Feature B: sulking & reconciliation

**New pure module `src/gitten/attention.py`** — same discipline as
`mood.py` / `status_badge.py` / `distraction.py`: no Qt imports, every
timestamp passed in by the caller. `AttentionTracker` tracks
`last_interaction_at` and a `state` (`NORMAL` / `SULKING`):

- `register_interaction(now)` — any click or drag, in any state, resets the
  clock. Called from `window.py`'s new `interacted` Qt signal, emitted on
  every mouse press regardless of button.
- `tick(now)` — promotes `NORMAL → SULKING` once `now - last_interaction_at
  >= 30 minutes`, mirroring `MoodMachine.tick()`'s pattern exactly.
- `register_pet(now)` — a plain click-in-place while `SULKING` increments
  `pets_received`; `turn_stage(pets_received)` maps that to the spec's 5
  discrete stages (0 = fully turned away .. 4 = fully reconciled), and
  hitting stage 4 flips the state back to `NORMAL` and resets the counter.
  No decay while partially reconciled, per the spec's explicit v1.2
  simplification — confirmed by a test that ticks the clock forward a long
  way mid-reconciliation and checks the partial stage holds steady.

**`sprite.py`** gained `_draw_face_turned(painter, center, stage, t)` and a
new optional `turn_stage: int | None` parameter on `paint_kitten` (default
`None`, so every existing call site — the tray icon, v1.1's tests — keeps
working unchanged, same additive-parameter pattern used for v1.1's
badges/nudge). Stage 0 draws a faint center seam and nothing else (fully
turned away); stages 1-3 progressively reveal a sliver of eye(s) and, at
stage 3, a small mouth, reading as "glancing back over a shoulder" without
changing the body/ear/tail proportions, so it's still recognizably the same
cat. Stage 4 isn't a real rendering path — reaching it in `attention.py`
means the state flips back to `NORMAL` and the normal front-facing
mood/badge rendering resumes untouched.

**The click-routing rule** (resolving the ambiguity between Features A and
B) lives in `main.py`, not `window.py`: `window.py` only knows "a plain
click happened while showing the pet view" (`plain_clicked` signal, emitted
from `mouseReleaseEvent` only when the release wasn't part of a drag and
`view_mode == "pet"`) and leaves the *meaning* of that click to
`GittenApp._on_plain_click()`, which checks `attention_tracker.state`:
`SULKING` → `register_pet()`; otherwise → open the inbox. This keeps
`window.py` ignorant of the sulking/inbox semantics, matching how it
already didn't know about mood-machine or distraction-tracker semantics
before this session.

### New timer

A 5-second `QTimer` (`_on_attention_tick`, same cadence as the existing
mood tick) calls `attention_tracker.tick()` so sulking kicks in even with
zero interaction, and re-applies the resulting `AttentionState`/`turn_stage`
to the window every tick — the same "periodic re-evaluation on top of
event-driven updates" pattern `mood.py`'s tick already established.

### Testing performed this session (v1.2)

- `pytest -q` → **62/62 passed**: the 43 pre-existing tests plus 11 new
  `test_attention.py` tests (default state, tick-seeds-the-clock,
  under/over the 30-minute threshold, interaction resets in any state, a
  drag/plain-interaction does *not* count as a pet, pets progressing
  through stages 1-3 without early reconciliation, the 4th pet fully
  reconciling, no-decay holding a partial stage steady, and petting while
  already `NORMAL` being a no-op pet that's still an interaction) and 8 new
  `test_notifications.py` tests for `format_notification` (multi-line
  joining, blank-line skipping, missing text/app-name fallbacks, and all
  four relative-time bands).
- **Feature A was verified against this machine's real, live Windows
  notification center**, not just mocked: `is_supported()` returned `True`,
  `request_access()` returned `True` (access was already granted on this
  machine), and `fetch_notifications()` returned actual real notifications
  present here (a Chrome extension-update toast and an Edge taskbar-pin
  prompt) with correctly formatted app names, joined text, and relative
  timestamps. This is a meaningfully stronger check than was possible for
  the v1.3 Telegram script, which has no test account available in this
  environment.
- Rendered all 4 sulking poses (`turn_stage=0..3`) plus the unchanged
  normal front view off-screen via `QPixmap` (`QT_QPA_PLATFORM=offscreen`)
  to confirm none of the new drawing code throws.
- Instantiated a full headless `GittenApp` and drove the new wiring
  end-to-end with real (non-mocked) calls: a plain click while `NORMAL`
  correctly opened the inbox and populated the list with the real
  notifications above; forcing `SULKING` and simulating 4 plain clicks
  correctly walked `turn_stage` through 0 and back to `NORMAL`
  (`pets_received` reset to 0) exactly as the unit tests predict in
  isolation.
- Caught and fixed a real off-by-one bug this way: an early version of
  `_resize_anchored_bottom_right()` computed the new top-left with plain
  `bottom_right - size` arithmetic, which is one pixel off because
  `QRect.bottomRight()` is inclusive (`x + width - 1`). A round-trip test
  (open the inbox, close it, assert the geometry is byte-for-byte identical
  to before) caught the drift immediately; fixed by using
  `QRect.moveBottomRight()` instead of manual arithmetic.

**What wasn't verified this session**: the inbox panel's and sulking
poses' actual on-screen appearance in a live running window (no interactive
desktop session available here, same limitation noted for v1.1) — the
off-screen renders and the headless wiring checks above confirm the code
paths run correctly and touch real data, but eyeballing the layout/spacing
of the inbox panel and the "glancing over its shoulder" poses on a real
screen is worth doing before considering v1.2 fully polished.

## 10. v1.3 (in progress) — Telegram connection, step 1: standalone script

Input is `GITTEN_V1_3_SPEC.md`, which adds a Telegram ("userbot") connection
that makes the kitten react differently to messages from favorite vs. bad
contacts. The spec is explicit that this is a new *category* of integration
(networked, credentialed) compared to everything built so far, and that the
connection itself should be built and proven solid as a small standalone
script before any of it touches `main.py`. **This session only did that
first step** — no tray menu entry, no `telegram_watcher.py`, no reaction
animations, and `main.py` was not touched at all. That's deliberate, not an
oversight: the spec's own hand-off instructions call out exactly this as the
first de-risking step.

### Security decisions made before writing any code

- Credentials (`api_id`/`api_hash`) and the Telethon session file live under
  `~/.gitten/`, the same directory the v1.1 distraction-list config already
  uses — never inside the project folder. This session never wrote a
  Telegram credential or session file anywhere under the repo checkout;
  `~/.gitten/` did not exist before this session and was confirmed empty
  after it (nothing was created because none of the interactive login flow
  ran — see "what wasn't tested" below).
- Added `.gitten/`, `*.session`, and `*.session-journal` to `.gitignore` per
  the spec's explicit "double-check `.gitignore` still correctly excludes
  anything under a local `.gitten/` if it's ever created inside the project
  folder by mistake" instruction. It didn't cover this before.
- The connection script never logs, prints, or otherwise surfaces the
  session file's contents.

### New files

```
src/gitten/
└── telegram_config.py          # pure path/JSON logic, no Telethon import
scripts/
└── telegram_connection_test.py # the standalone script itself
tests/
└── test_telegram_config.py     # 7 tests
```

**`telegram_config.py`** follows the same discipline as `mood.py` /
`distraction.py`: pure functions, no I/O side effects beyond explicit
read/write calls, and — critically for this feature — no Telethon import,
so it's testable without touching the network or a live account. It owns
exactly one thing: where `telegram_config.json` and the `telegram.session`
stem live (`~/.gitten/`) and how to load/save the cached `api_id`/`api_hash`
pair. This was pulled out of the standalone script into a proper module
under `src/gitten/` (rather than being inlined in `scripts/`) because
`telegram_watcher.py` will need the exact same logic once it's built next —
one source of truth for "where do these files go" avoids re-deriving it
later and risking a path drift bug that writes a credential somewhere
uninspected.

**`scripts/telegram_connection_test.py`** is the actual de-risking script
called for by the spec: it loads (or interactively prompts for and caches)
`api_id`/`api_hash`, opens a `TelethonClient` pointed explicitly at
`~/.gitten/telegram` as its session path (never letting Telethon default
into the current working directory), calls Telethon's built-in
`client.start()` interactive login (phone number, then the code Telegram
texts/sends, then a 2FA password if the account has one — reusing
Telethon's own console prompts rather than reimplementing them, since a
one-off CLI script doesn't need the Qt dialogs the spec asks for in the
*real* tray feature), registers a `NewMessage` handler, and prints
`[@username or id:12345] message text` for every incoming message. Run
directly with `python scripts/telegram_connection_test.py`.

Added `telethon>=1.36` to `pyproject.toml`'s main `dependencies` (it will be
a runtime dependency of the shipped app once `telegram_watcher.py` exists,
not just a dev/test tool) and installed it into the existing `.venv`.

### Testing performed this session

- `pytest -q` → **43/43 passed** (36 pre-existing + 7 new
  `test_telegram_config.py` tests covering: default paths resolve under
  `~/.gitten` and not under a project-folder stand-in, missing config file →
  `None`, invalid JSON → `None`, missing keys → `None`, a save/load
  round-trip, parent-directory creation on save, and a hand-edited
  string-typed `api_id` still loading correctly as an int).
- Verified `scripts/telegram_connection_test.py` compiles
  (`py_compile`), parses (`ast.parse`), and imports cleanly with Telethon
  installed, without triggering the interactive login path.
- After that import, confirmed `~/.gitten/` still did not exist on disk —
  proof that nothing in the module-load path writes a credential or session
  file as a side effect of merely importing the script.
- Printed the resolved `DEFAULT_SESSION_PATH` / `GITTEN_DIR` constants and
  confirmed they point at `C:\Users\<user>\.gitten\...`, well outside the
  project checkout.

**What wasn't tested this session, and why:** the actual live Telegram
login (entering a real `api_id`/`api_hash`, phone number, and login code)
was **not** run, because doing so requires a real Telegram account's
credentials and an interactive terminal to receive the login code — neither
is available in this environment, and per the spec's own security section
these credentials must never be typed into, generated for, or stored by an
automated session on the user's behalf. **This is the one thing to verify
by hand before trusting the connection**: run
`python scripts/telegram_connection_test.py` yourself, supply your own
`api_id`/`api_hash`/phone/code, send yourself (or have someone send you) a
Telegram message, and confirm it prints with the right sender label. Once
that's confirmed working, the next step is building `telegram_watcher.py`
(the Qt-integrated, thread-based version with the favorites/bad list
matching and signal emission) and only then wiring it into `main.py`.

## 11. Housekeeping this session: README accuracy & GitHub About description

Two small, non-feature fixes bundled into this session per instructions:

- **README's "Project structure" section was stale**: it still only listed
  the v1 file set (`main.py`, `window.py`, `sprite.py`, `mood.py`,
  `git_watcher.py`) even though v1.1 had already added `status_badge.py`,
  `distraction.py`, `system_monitor.py`, and `foreground_window.py`, and
  this session added `attention.py`, `notifications.py`, and
  `telegram_config.py` plus the `scripts/` folder. Updated the tree to list
  every module that actually exists on disk, with a one-line description
  of each in the same style the section already used.
- **The GitHub repository's "About" description was still the placeholder
  "funny cat"**. The GitHub CLI (`gh`) is not installed in this
  environment (`gh: command not found`), so it couldn't be updated
  directly with `gh repo edit --description "..."` — the exact text to
  paste into the repo's About panel on github.com was given to the user
  instead, derived from the README's first paragraph.

Also added `GITTEN_V1_4_SPEC.md` to version control -- the user dropped it
in the project folder for a future session (streaks, focus mode, combo
alert, random one-liners) but explicitly said not to start it yet, so it's
committed as a plain doc with no accompanying code, same as how the other
spec files were tracked before their features were built.

## 12. v1.4 -- streaks, focus mode, combo alert, random one-liners

Input is `GITTEN_V1_4_SPEC.md`, four independent features to be built one at
a time, each tested and documented before moving to the next, and committed
separately.

### Feature 1: Daily commit streak

**New pure module `src/gitten/streak.py`** -- same discipline as `mood.py`:
one function, `compute_streak(commit_dates: Iterable[str], today: date) ->
int`, zero Qt/subprocess imports. It dedupes the input into a `set` of
`date` objects, then counts backward one day at a time starting from `today`
if today already has a commit, or from `today - 1` if it doesn't (so the
streak isn't considered broken just because it's still early in the day) --
the first missing day stops the count. `today` is passed in by the caller
(the same "inject the clock" idiom `mood.py` uses for `now`) rather than
read internally, so it's fully unit-testable with fake dates.

**`git_watcher.py`** gained `get_commit_streak(repo_path) -> int | None`,
built the same way `count_commits_today` already was: `git log
--format=%ad --date=short`, deduped into a set of date strings, fed into
`compute_streak(dates, date.today())`. Recomputed from the full log every
call rather than kept as a running counter, exactly as the spec asks (a
running counter could silently drift if the app were closed for a day and
reopened, or if commits were made outside Gitten's watch).

**`sprite.py`** gained an optional `streak: int = 0` parameter on
`paint_kitten` (default 0, so existing call sites are unaffected) and a new
top-right icon slot (`_STREAK_POS_OFFSET`, mirroring the badge's top-left
slot from v1.1 and deliberately placed away from the mood overlay which
lives top-center/right) -- nothing below 3 days, a small grey star at 3-6, a
bigger gold twinkling star at 7-29 (`_draw_star_icon`, a 5-point star path
with a slow sine "twinkle" on its radius), and a small gold crown at 30+
(`_draw_crown_icon`, a 7-point zigzag polygon: two flat bottom corners and a
3-spike zigzag top, middle spike tallest).

**`window.py`** gained `set_streak(streak: int)` (same no-op-if-unchanged
pattern as `set_badge`) and threads `streak=self._streak` through to
`paint_kitten` in `paintEvent`.

**`main.py`**: `_apply_streak()` calls `get_commit_streak` (0 if no repo is
watched) and pushes it to the window, called from both `_on_commit` (so the
star/crown appears immediately after a commit that extends the streak) and
the existing 5-second `_on_tick` (so it also stays correct as days roll over
with no new git event to trigger it). The right-click stats menu
(`_show_context_menu`) gained a `Streak: N day(s)` line right after "Commits
today", using the same `get_commit_streak` call.

**Testing**: `pytest -q` -> **71/71 passed** (62 pre-existing + 9 new
`test_streak.py` tests: empty list, a single commit today, a single commit
only yesterday, no commit in the last two days, a 3-day streak including
today, a 3-day streak ending yesterday, a gap breaking the streak, duplicate
same-day commits not inflating the count, and accepting a `set` as well as a
`list`). Also verified end-to-end against a real scratch git repo (three
commits on three consecutive days, backdated via `GIT_AUTHOR_DATE`/
`GIT_COMMITTER_DATE`): `get_commit_streak` correctly returned `3` and
`count_commits_today` returned `1`. Rendered all four streak tiers (`0`,
`3`, `7`, `30`) through `paint_kitten` on an off-screen `QPixmap`
(`QT_QPA_PLATFORM=offscreen`, with an explicit `QApplication` instance --
without one, `QPixmap` construction crashes the interpreter outright rather
than raising a catchable Python exception, a small gotcha worth remembering
for any future off-screen render check in this environment) to confirm none
of the new drawing paths throw.

### Feature 2: Focus reaction while tests/builds run

**New pure module `src/gitten/focus.py`** -- same split as `distraction.py`:
`matches_focus_process(cmdline, substrings)` is a case-insensitive substring
match against one process's full command line, and
`load_focus_substrings(path)` reads a user-editable JSON file
(`~/.gitten/focus_config.json`, `{"substrings": [...]}`) falling back to the
spec's defaults (`pytest`/`npm test`/`npm run build`/`cargo test`/`go test`)
if missing or invalid -- exactly the same JSON-file-in-`~/.gitten/` pattern
`distraction.py` established. Neither function touches `psutil`.

**The actual `psutil.process_iter()` sweep lives in `system_monitor.py`**,
not in `focus.py` -- that file is already this project's "thin I/O boundary"
for psutil (per its own module docstring), the same split already used for
`foreground_window.py` (win32 I/O boundary) vs. `distraction.py` (pure
matching logic). The new `is_focus_process_running(substrings)` iterates
`psutil.process_iter(["cmdline"])`, joins each process's `cmdline` list into
one string, and checks it with `matches_focus_process`; a process that
disappears or denies access mid-scan (`NoSuchProcess`/`AccessDenied`) is
skipped rather than aborting the whole sweep, since that's routine on a
system with many short-lived processes.

**Being upfront about the limitation the spec calls out**: this only
answers "is a matching process currently running", never whether it passed
or failed. Gitten observes processes rather than launching them, so exit
codes/log output aren't available to it -- guessing pass/fail from log
files would be fragile (different tools format output differently, and a
still-running process has no exit code yet) and was deliberately not
attempted, per the spec's explicit instruction. The reaction is therefore
framed purely as "watching" -- see rendering below -- with no pass/fail
opinion at all.

**`sprite.py`** gained an optional `focused: bool = False` parameter on
`paint_kitten`. `_draw_ears` gained a `perked: bool = False` parameter
(height scaled up 1.3x and leaning in toward center instead of splaying out,
an alert posture) and a new `_draw_focused_face` draws wide white eyes with
pupils that stay fixed dead ahead (a slow size-pulse standing in for
"concentrating", no eyebrows) and a small flat neutral mouth -- deliberately
different from the WAITING mood's nervous side-to-side glancing pupils and
worried eyebrows, since "watching a test run" isn't the same feeling as
"anxious about uncommitted changes". Precedence: sulking (`turn_stage`)
still wins over focus -- a mid-sulk cat doesn't perk up for a test run --
computed once as `show_focused = focused and turn_stage is None` and used
for both the ear posture and the face/mood-overlay branch, so the two never
render inconsistently with each other.

**`window.py`** gained `set_focused(bool)` (same no-op-if-unchanged pattern
as `set_badge`/`set_streak`) and threads it through to `paint_kitten`.

**`main.py`**: `self.focus_substrings` is loaded once at startup via
`load_focus_substrings(DEFAULT_FOCUS_CONFIG_PATH)`. A new 5-second
`QTimer` (`_on_focus_tick`, the same cadence as the attention tick) calls
`is_focus_process_running(self.focus_substrings)` and pushes the result
straight to `window.set_focused(...)` -- no tracker/state machine needed
since, unlike mood or distraction, this reaction has no streak/threshold
logic at all, just "is one running right now".

**Testing**: `pytest -q` -> **82/82 passed** (71 pre-existing + 11 new
`test_focus.py` tests: each of the five default substrings matching,
case-insensitivity, an unrelated process not matching, custom substrings
overriding the defaults, and the three `load_focus_substrings` file-loading
cases mirroring `test_distraction.py`'s). Rendered `focused=True` combined
with each mood (`IDLE`/`HAPPY`/`WAITING`), `focused=True` together with
`turn_stage=1` (confirming sulking still wins -- no exception and the
turned-face path is what actually draws), and `focused=False`, all through
an off-screen `QPixmap`. Also did a real end-to-end check of
`is_focus_process_running`: called it with nothing matching running
(`False`), then launched a real `python -m pytest --collect-only -q`
subprocess and called it again while that process was alive (`True`), then
again after it exited (`False`) -- confirming the psutil sweep actually
detects a real matching process by its command line, not just by mocked
input.

### Feature 3: Verify (and lightly enhance) the low-battery + uncommitted-changes combo

**Verified first, before writing any code**, per the spec's explicit
instruction not to just assume it. `mood.py` (git-driven) and
`status_badge.py` (system-driven) were built in v1 and v1.1 respectively as
deliberately independent state machines, and `sprite.py`'s
`_draw_status_badge` call already sits outside the `if turn_stage is
None: ...` mood-face branch, so nothing about the badge's rendering was ever
conditioned on mood. Confirmed this concretely rather than just reading the
code: drove a real `MoodMachine` into `WAITING` (via `update_dirty` +
`tick` past the threshold) and a real `StatusBadgeTracker` into
`CRITICAL_BATTERY` (10 sustained low-battery samples), rendered both
together through `paint_kitten` on an off-screen `QPixmap`, and diffed that
image against a `WAITING`-with-no-badge render and an `IDLE`-with-the-same-
badge render -- in both comparisons the exact same 150 pixels differed
(the badge icon's silhouette), proving the badge renders identically
regardless of mood and the two layers really are fully independent, with
**no new code**.

**The one small deliberate touch added**: `paint_kitten` now computes
`urgent = badge in (Badge.LOW_BATTERY, Badge.CRITICAL_BATTERY)` and passes
it through `_draw_mood_overlay` to `_draw_exclaim_bubble`, which swaps the
WAITING bubble's text from `"!"` to `"‼"` (U+203C, DOUBLE EXCLAMATION MARK)
when `urgent` is true -- a pure rendering-time string choice, read fresh on
every paint from whatever `badge`/`mood` happen to be current, with no new
state stored anywhere.

**A genuine limitation of this sandboxed test environment surfaced while
verifying the glyph swap, worth recording for future sessions**: comparing
rendered pixels of `"!"` vs `"‼"` off-screen came back bit-for-bit
identical (0 differing pixels) at first, which looked like a bug. Chased it
down with `QFontDatabase.families()`, which returned an **empty list** --
`QT_QPA_PLATFORM=offscreen` in this environment has zero fonts installed at
all, so every character (any character) falls back to the same
missing-glyph placeholder box, regardless of which one was actually
requested. This is an environment artifact, not an app bug -- confirmed by
monkey-patching `QPainter.drawText` to spy on its string argument instead of
comparing rendered pixels: `_draw_exclaim_bubble(..., urgent=False)`
genuinely calls `drawText` with `"!"` and `urgent=True` genuinely calls it
with `"‼"`, two distinct strings. **This is the one thing to eyeball on a
real Windows desktop before considering this feature fully verified** (real
Segoe UI, unlike this sandbox, does have the U+203C glyph) -- the same
category of "couldn't verify live rendering in this environment" limitation
already noted for v1.1's badges/nudge and v1.2's inbox panel/sulking poses.

No new tests file: the spec explicitly asks for no new state machine, and
`sprite.py` has never had a `test_sprite.py` (it's always been verified via
off-screen `QPixmap` renders per the project's established pattern, not
pytest, since it's pure drawing code with no branching logic worth unit
testing in isolation). `pytest -q` was re-run anyway after this feature's
changes to confirm nothing regressed: **82/82 passed** (unchanged from
Feature 2, since this feature added no new pure-logic module).

### Feature 4: Random cute one-liners

**New pure module `src/gitten/oneliners.py`** -- three small pieces, all
following the same "inject the nondeterministic input" idiom `mood.py` uses
for the clock, applied here to the RNG instead (`rng: random.Random | None
= None`, defaulting to the module-level `random` in production but
seedable in tests):

- `ONELINERS` -- the starter list (the spec's four example lines plus six
  more in the same short, friendly, programmer-flavored Persian tone).
- `random_interval_seconds(rng, min_minutes=45, max_minutes=90)` -- a
  uniform random interval for the next one-liner.
- `pick_oneliner(rng)` -- a random line from the list.
- `should_show_oneliner(view_mode, is_sulking, is_nudging)` -- the pure
  decision of whether *now* is a good moment to interrupt: only when
  `view_mode == "pet"` and neither sulking nor already showing another
  nudge. Deliberately takes plain `str`/`bool` arguments rather than
  importing `AttentionState` or any Qt type, so it stays trivially testable
  and `window.py`/`main.py` stay the source of truth for what those states
  actually mean.

No new rendering was needed, per the spec: this reuses `window.py`'s
existing `show_nudge` / opacity-fade timeline unchanged. The one small
addition to `window.py` is a read-only `is_nudging` property (`self.
_nudge_text is not None`) so `main.py` can check "is a nudge already
showing" without reaching into the window's private state.

**`main.py`** wiring: a single-shot `QTimer` (`_oneliner_timer`) is
(re)started with `random_interval_seconds() * 1000` ms both at startup and
at the end of every firing (`_schedule_next_oneliner`), so the cadence is
freshly randomized each time rather than fixed. `_on_oneliner_timer` checks
`should_show_oneliner(self.window.view_mode, is_sulking, self.window.
is_nudging)` -- `is_sulking` read from `self.attention_tracker.state`, the
same source of truth `_apply_attention` already uses -- and calls
`self.window.show_nudge(pick_oneliner())` only if it returns `True`;
either way the next occurrence is always rescheduled, so a skipped
occurrence doesn't mean waiting an extra cycle, it's just silently dropped
and tried again next time per the spec ("skip and reschedule rather than
interrupting something else"). A comment notes that there's no
"mid-Telegram-alert" state to check yet, since the v1.3 Telegram reactions
were deliberately never wired into `main.py` (see section 10) -- that
check should be added here once they are, so a future session doesn't miss
it.

**Testing**: `pytest -q` -> **92/92 passed** (82 pre-existing + 10 new
`test_oneliners.py` tests: interval bounds held across 500 seeded draws,
custom min/max bounds respected, determinism given the same seed,
`pick_oneliner` always returning a list member, the starter list having at
least 8 lines, and all four `should_show_oneliner` combinations -- shows
when clear, skips when sulking, skips when already nudging, skips when in
the inbox view, and skips when everything is going on at once). Also ran a
full headless end-to-end check against a real, running `GittenApp`
instance (not mocked): forced each of the four gating states in turn and
called `_on_oneliner_timer()` directly -- confirmed it actually calls
`window.show_nudge(...)` with one of the real Persian lines when idle in
the pet view, correctly does nothing when sulking or in the inbox view
(while still leaving the timer active/rescheduled for next time), and does
not overwrite an already-showing nudge's text. Separately rendered all 10
one-liners through `paint_kitten`'s existing nudge-bubble path off-screen
to confirm none of them throw.

With this, all four v1.4 features are implemented, tested, and documented.

## 13. v1.5 -- interactive & time-based personality features

Input is `GITTEN_V1_5_SPEC.md`, 7 features, same "one at a time, in order,
test + document before moving on, separate commits" process as v1.4.
Features 1-3 deliberately build on a shared particle system and were kept
in that exact order.

### Feature 1: Sparkle particle system (foundation for 2 and 3)

**New pure module `src/gitten/particles.py`** -- same pure/Qt split as
`mood.py` vs. `sprite.py`: a `Particle` dataclass (`x`, `y`, `spawned_at`,
`lifespan`, `dx`/`dy` drift) and a `ParticleSystem` with `spawn_particle(x,
y, now, lifespan, dx, dy)`, `update_and_prune(now)` (drops anything past
its lifespan), and `positions(now) -> list[(x, y, opacity)]` (position
advanced by drift, opacity fading linearly to 0). Deliberately generic --
nothing here mentions dragging or shooting stars -- so Feature 3 can reuse
it unchanged for a very different visual just by spawning with a longer
lifespan and a drift vector instead of Feature 2's short-lived, stationary
sparkles.

**One deliberate deviation from the spec's suggested `spawn_particle` /
`update_and_prune` / `draw_particles` shape**: `draw_particles` itself
lives in `sprite.py`, not on `ParticleSystem`, taking the plain `(x, y,
opacity)` tuples `positions()` already computes. This keeps `particles.py`
completely Qt-free and unit-testable with fake timestamps, the same
discipline every other pure module in this project follows (`focus.py`'s
matching logic vs. `system_monitor.py`'s psutil sweep is the closest
precedent) -- worth calling out explicitly here since the spec's own
wording suggested drawing could live on the same object.

**Testing**: `pytest -q` -> **99/99 passed** (92 pre-existing + 7 new
`test_particles.py` tests: an empty system, a freshly spawned particle at
full opacity, linear opacity fade to 0.5 at the halfway point,
`update_and_prune` dropping an expired particle and keeping a still-alive
one, drift correctly advancing position over elapsed time, and multiple
particles tracked independently). Rendered `draw_particles` off-screen with
a batch of particles at several points across their lifespan (including one
past expiry, and an empty list) to confirm none of it throws.

### Feature 2: Sparkle trail while dragging

`window.py` gained a `ParticleSystem` instance (`self._particles`) and a
throttled spawn helper, `_maybe_spawn_drag_particle`, called from
`mouseMoveEvent` only while `self._dragging` is true. Since `mouseMoveEvent`
can fire far more often than the 30fps repaint timer during a fast drag,
spawning is throttled to roughly every other animation frame
(`_DRAG_PARTICLE_INTERVAL_SECONDS = 2 * ANIMATION_INTERVAL_MS / 1000`) using
a `time.monotonic()` timestamp check, the same throttle idiom
`git_watcher.py`'s index-change debounce already uses. Particles are
spawned at `event.position()` -- real widget-local pixel coordinates, no
drift (`dx=dy=0.0`) -- and given a shorter lifespan (0.5s) than the
particle system's 0.7s default, so the trail reads as a quick shimmer
rather than lingering.

**Drawing happens outside `paint_kitten`'s canvas transform, deliberately**:
`paint_kitten` immediately translates/scales into its own fixed 128x128
logical space, but drag-trail particles are spawned in real widget pixel
coordinates (from `QMouseEvent.position()`), not that internal canvas space.
So `paintEvent` calls `self._particles.update_and_prune(now)` +
`draw_particles(painter, self._particles.positions(now))` on the raw
painter *before* calling `paint_kitten` (which does its own `save()` /
`restore()` around its transform), rather than threading particle positions
through `paint_kitten`'s parameters the way badges/streak/nudge are. This
also means the trail is purely cosmetic and window-owned, with no coupling
to the kitten's own drawing code at all -- matching the spec's "no new
state beyond what Feature 1 already provides."

**Testing**: `pytest -q` -> still **99/99 passed** (no new pure-logic
module, so no new test file -- this feature is Qt wiring only, verified
the same way `window.py`/`sprite.py` changes always have been in this
project: real Qt objects, off-screen). End-to-end: instantiated a real
`KittenWindow`, sent a synthetic `QMouseEvent` press to start a drag, then
5 synthetic move events spaced 0.1s apart (monkeypatching
`time.monotonic` for determinism) -- confirmed exactly 5 particles were
spawned (one per move, since each move crossed the throttle interval).
Then sent 5 more move events spaced only 1ms apart -- confirmed only 1
additional particle spawned (the rest correctly throttled). Finally called
`window.grab()` (a real off-screen render of the live widget, not just
`paint_kitten` directly) while particles were active mid-fade to confirm
`paintEvent` doesn't throw with the new particle-drawing call in it.

### Feature 3: Rare random event (shooting star)

### Feature 3: Rare random event (shooting star)

**`oneliners.py`** gained `should_show_rare_event(rng=None, probability=0.05)`,
following the exact same injectable-RNG shape as `random_interval_seconds`/
`pick_oneliner`: `rng.random() < probability`.

**`window.py`** gained `trigger_shooting_star()`, which reuses Feature 1's
`ParticleSystem` completely unchanged -- it just spawns *one* particle at
the top-left corner `(0, 0)` with a drift vector computed so it reaches the
bottom-right corner `(width, height)` exactly at the end of its 1-second
lifespan (`dx = width / 1.0`, `dy = height / 1.0`), fading the whole way per
`ParticleSystem`'s existing linear opacity falloff. No new drawing code at
all -- `draw_particles` (already wired into `paintEvent` for Feature 2)
renders it exactly like a drag-trail sparkle, just one that travels much
further and lives much longer.

**`main.py`**'s `_on_oneliner_timer` now checks `should_show_rare_event()`
*inside* the existing `should_show_oneliner(...)` branch -- so the rare
event only gets a chance to fire on an occurrence that would have shown a
one-liner anyway (same gating: idle pet view, not sulking, not already
nudging), and when it doesn't fire, the normal `pick_oneliner()` nudge
plays exactly as before. This matches the spec precisely: "each time it
fires and `should_show_oneliner(...)` returns `True`, add a small chance...
that instead of a normal text bubble, a shooting star plays instead."

**Testing**: `pytest -q` -> **104/104 passed** (99 pre-existing + 5 new
`should_show_rare_event` tests in `test_oneliners.py`: the observed fraction
over 20,000 seeded draws landing within a generous tolerance band of the
default 5% probability, a custom 50% probability similarly landing near
50% over 5,000 draws, probability 0.0 never firing across 1,000 draws,
probability 1.0 always firing across 1,000 draws, and determinism given a
seeded RNG). End-to-end: instantiated a real `GittenApp`, forced the idle
gating state, and patched `gitten.main.should_show_rare_event` to always
return `True` -- confirmed the real `_on_oneliner_timer` code path calls
`trigger_shooting_star()` (not `show_nudge`), that it added exactly one new
particle starting at `(0, 0)` with a positive `dx`/`dy` and `lifespan ==
1.0`, and that no nudge bubble text was set. Then patched it to always
return `False` and confirmed the normal one-liner nudge path still fires
as before.

### Feature 4: Purr on hover

### Feature 4: Purr on hover

**`window.py`** overrides Qt's `enterEvent`/`leaveEvent` to track a plain
`self._hovering: bool`, threaded through to `paint_kitten` as a new
`hovering` parameter -- no debouncing needed since Qt only fires these once
per actual enter/leave of the widget's region, not per pixel of mouse
movement.

**`sprite.py`**: precedence is computed once, mirroring exactly how
`show_focused` was computed in v1.4 Feature 2 (`show_focused = focused and
turn_stage is None`), extended with one more layer:

```python
show_purr = hovering and turn_stage is None
show_focused = focused and turn_stage is None and not show_purr
```

Sulking (`turn_stage is not None`) still wins over both, per the spec.
Between hover and focus, purring additionally wins whenever both are true
at once -- a judgment call this session made explicitly (the spec only
specifies precedence against sulking/inbox, not against `focused`): a live
hover is a more immediate, direct interaction signal than a passive
background test run, so it makes sense for the cat to visibly notice being
petted even mid-test-run, reverting the instant the cursor leaves. Verified
concretely, not just reasoned about: rendered `hovering=True` combined with
`turn_stage=1` and diffed the image against a plain `turn_stage=1` render
with no hover -- **zero pixels differed**, confirming sulking truly
suppresses the purr face with no leakage, versus a non-sulking hover-vs-no-
hover comparison which differed by 608 pixels (the purr face genuinely
changes the render).

`view_mode == "pet"` -- the third condition the spec's `show_purr` formula
names -- isn't threaded through `paint_kitten` as its own parameter,
deliberately: `window.py`'s `paintEvent` already returns early without
calling `paint_kitten` at all whenever `view_mode == "inbox"` (this was
already true before this feature, for the exact same reason `turn_stage`
rendering never had to separately check the inbox view either), so it's
already guaranteed true by the time `paint_kitten` runs at all. Documented
inline in `sprite.py` so a future session doesn't wonder where the third
condition went.

`_draw_ears` gained a `wiggle: bool` + `t: float` pair alongside the
existing `perked` flag: a small sine-wave sway on the ear tips (`2.5 *
sin(t * 3.0)`), the same breathing/tail-sway idiom reused a third time. A
new `_draw_purr_face` draws squinted-but-not-fully-closed eyes (distinct
from IDLE's fully-closed sleep curves) with a gentle upward smile and no
zzz/heart/bubble overlay, matching the "distinct from mood-driven
happy/idle/waiting faces" requirement.

**Testing**: `pytest -q` -> still **104/104 passed** (no new pure-logic
module -- this is Qt wiring + drawing only). Rendered every combination
off-screen (`hovering` with each of the three moods, `hovering` +
`focused`, `hovering` + `turn_stage`, and no hover) to confirm none throw;
sent a real `QEnterEvent`/`QEvent.Leave` through a live `KittenWindow` and
confirmed `_hovering` flips both ways correctly; and did the pixel-diff
precedence proof described above.

### Feature 5: High-five on double-click

### Feature 5: High-five on double-click

**The conflict the spec flagged, confirmed and resolved exactly as
described**: Qt delivers a double-click as `mousePressEvent` ->
`mouseReleaseEvent` -> `mousePressEvent` -> `mouseDoubleClickEvent` ->
`mouseReleaseEvent` -- the *first* release already looks exactly like a
complete, ordinary single click by the time it arrives, before Qt has told
us a second one is coming. Before this feature, `mouseReleaseEvent` acted
immediately on that first release (`plain_clicked.emit()`), which would
have both opened the inbox (or registered a pet while sulking) **and**
triggered the high-five on every double-click.

**Fix**: `mouseReleaseEvent` no longer emits `plain_clicked` immediately.
Instead, when a release qualifies as a plain click (`was_plain_click and
view_mode == "pet"`), it starts a single-shot `_click_pending_timer` using
`QApplication.doubleClickInterval()` -- deliberately the *same* interval
Qt's own double-click detector uses internally, not an arbitrary
hardcoded number, so a genuine second click is mathematically guaranteed to
arrive (and be seen as `mouseDoubleClickEvent`) before our timer could fire
first. Only when that timer actually elapses with nothing having cancelled
it does `_on_click_confirmed_single()` finally emit `plain_clicked`. This
applies uniformly to **both** existing single-click meanings (inbox-open
and pet-registration) since neither `window.py` nor `main.py`'s
`_on_plain_click` needed to change at all -- the disambiguation lives
entirely upstream of the existing signal, per the spec's explicit
instruction not to bypass it for either one.

`mouseDoubleClickEvent` (new) stops `_click_pending_timer` (cancelling
the deferred single-click action outright) and calls `_trigger_high_five()`.
One more subtlety this session had to work through by hand-tracing the Qt
event sequence: the *second* click's own trailing `mouseReleaseEvent` still
arrives right after `mouseDoubleClickEvent` fires, and without any guard it
would itself look like a fresh plain click and queue up a *second*,
spurious pending single-click action ~400ms later. Fixed with a
`self._just_double_clicked` flag, set in `mouseDoubleClickEvent` and
consumed (reset, without starting a new pending timer) by the very next
`mouseReleaseEvent`.

**The high-five animation itself**: `_trigger_high_five()` sets
`self._high_fiving = True`, repaints, and calls `QTimer.singleShot(1300,
self._clear_high_five)` -- the "boolean flag + `QTimer.singleShot` to clear
it" idiom the spec pointed at (v1.3's Telegram alert lifecycle was
mentioned as prior art for this idiom, though per section 10 that lifecycle
was never actually wired into `main.py` -- this is the first place in the
codebase the pattern is actually implemented). Rendering-wise,
`_draw_high_five_paw` (new in `sprite.py`) doesn't touch the face or mood
at all -- it's a small raised paw pad with three toe bumps, gently
wobbling, drawn as the very last thing in `paint_kitten` regardless of
mood/sulking/purr/focused. Keeping it purely additive like this sidesteps
any precedence question entirely (no face-override conflict to resolve)
and means even a mid-sulk double-click gets a quick, charming high-five
before reverting to the turned-away pose once it clears.

**Testing**: `pytest -q` -> still **104/104 passed** (Qt wiring + drawing
only, no new pure-logic module). End-to-end, with real synthetic
`QMouseEvent`s driven through a live `KittenWindow` and a real Qt event
loop (`app.processEvents()` pumped across the actual
`QApplication.doubleClickInterval()`, 400ms in this environment): (1) a
genuine single click emits `plain_clicked` exactly once, only after the
interval elapses, never before, and never triggers `_high_fiving`; (2) a
genuine double-click (press/release/press/doubleClick/release) sets
`_high_fiving` immediately and **never** emits `plain_clicked` -- not on
the first release, not on the trailing release, and not even after waiting
well past the interval, confirming the leaked-second-action bug described
above is actually fixed, not just theorized about; (2b) `_high_fiving`
self-clears back to `False` after its ~1.3s duration; (3) a real drag
(press, move past the threshold, release) triggers neither action.
Separately rendered `high_five=True` combined with sulking, with hovering,
and alone, off-screen, to confirm the additive paw overlay never throws
regardless of what else is showing.

### Feature 6: Nameable cat

### Feature 6: Nameable cat

`main.py` loads `self.cat_name = self.settings.value("cat/name",
DEFAULT_CAT_NAME)` at startup (`DEFAULT_CAT_NAME = "Gitten"`) and adds a
"Rename..." tray menu entry, right next to "Choose watched repo..." (built
together with Feature 7's "Set my birthday..." per the spec's suggestion --
both are simple one-time `QSettings`-backed `QInputDialog` prompts).
`_prompt_rename()` uses `QInputDialog.getText(..., text=self.cat_name)` so
the field is pre-filled with the current name, only commits the change on
`ok and name.strip()` (a cancelled dialog or an all-whitespace name is a
no-op, not a reset to blank), and persists via
`self.settings.setValue("cat/name", self.cat_name)` -- the same `QSettings`
object already used for window position/watched repo.

A new `_update_tray_tooltip()` helper is now the single place that sets the
tray tooltip (`"{name} -- watching {path}"` or just `"{name}"` with no repo
chosen), replacing two previously-separate hardcoded tooltip strings in
`_build_tray` and `_prompt_choose_repo` -- so renaming immediately updates
the tooltip without those two call sites needing to independently remember
to include the name.

The stats menu gained a `"-- {name} --"` header line (ASCII double-hyphen,
matching this codebase's existing convention of writing `--` instead of an
em-dash everywhere else in UI/doc text, rather than the spec example's
literal em-dash) as the first entry, above the existing Streak/Commits-
today/battery/repo/uptime lines.

**A real testing obstacle hit and worked around**: this session first
tried to verify the stats menu's header text by monkeypatching
`QMenu.exec` with `unittest.mock.patch.object` (to avoid actually blocking
on a real popup in this headless environment) and calling
`_show_context_menu` directly. That didn't just fail to work -- it silently
corrupted the `QMenu` instance entirely: a `QMenu()` built and populated
*inside* the same `with patch.object(...)` block came back from
`.actions()` as an *empty list*, even though `addAction` had definitely
been called on it, with no error raised anywhere. Patching a compiled
Shiboken-bound Qt method this way is evidently unsafe in this PySide6
version, not just ineffective, and a naive test relying on it would have
silently reported false confidence. **Fixed properly, not worked around**:
extracted the menu's info-line text into a new `_stats_menu_lines(self) ->
list[str]` helper (pure list-of-strings logic, called by
`_show_context_menu` to build the actual disabled `QAction`s) so the header
text can be exercised directly with a plain function call and no `QMenu`
involved at all -- no monkeypatching of any kind needed. Worth remembering
for future sessions: don't monkeypatch Qt/Shiboken class methods
(`QMenu.exec`, and likely other compiled Qt methods generally) to avoid a
blocking call in tests; refactor the piece worth testing out into a plain
Python helper instead.

**Testing**: `pytest -q` -> still **104/104 passed** (no new pure-logic
*module* -- `_stats_menu_lines` lives on `GittenApp` itself, closer to the
class's existing untested Qt-wiring methods than to a `mood.py`-style
standalone module, so it wasn't worth a separate test file for one method).
End-to-end against a real `GittenApp`: confirmed the default name is
`"Gitten"` and appears in the initial tray tooltip; patched
`QInputDialog.getText` to return `("Whiskers", True)` and confirmed
`cat_name` updated, the tooltip updated to include it alongside the watched
repo path, and the value round-tripped through the real (registry-backed)
`QSettings` -- read back via a *separate* fresh `QSettings("Gitten",
"Gitten")` handle, not just the same object, to prove real persistence
rather than in-memory state; confirmed a cancelled dialog (`ok=False`) and
an all-whitespace name (`"   "`) both correctly leave the name unchanged;
and confirmed `_stats_menu_lines()` returns the `"-- {name} --"` header as
its first element. The registry-backed settings value was reset back to
the default at the end of the check script so this session's testing
doesn't leave a stray "Whiskers" behind for the real app.

### Feature 7: Seasonal accessories & day/night palette

### Feature 7: Seasonal accessories & day/night palette

**New pure module `src/gitten/seasons.py`**, same discipline as
`streak.py`: `seasonal_accessory(today: date, birthday: date | None =
None) -> str | None` (the spec's signature only names `today`; `birthday`
was added as an optional keyword parameter so the function stays simple to
call for the two fixed-calendar cases while still supporting the third)
returns `"halloween"` (Oct 31), `"yalda"` (~Dec 21), `"birthday"` (matching
month/day, birth year ignored), or `None` -- fixed calendar occasions are
checked before the birthday, a deliberate priority choice for the (very
unlikely) case of a birthday landing on Halloween or Yalda, covered by its
own test. `is_night_time(hour: int) -> bool` is a plain range check,
23:00-7:00.

**Rendering**: `paint_kitten` gained `accessory: str | None = None` and
`night: bool = False`. The accessory renders via a new `_draw_accessory`
dispatcher at a dedicated top-center spot (`_ACCESSORY_POS`, directly above
the head) -- distinct from the badge (top-left) and streak (top-right)
corner icons, since (per the spec) a hat reads as "worn" rather than
"floating beside": a black witch hat with a purple band for Halloween, a
small red pomegranate with a green calyx for Yalda (the fruit's iconic
silhouette, matching the occasion's traditional symbol), and a gradient-
striped party hat with a white pom-pom for a birthday. Night is a pure
rendering-time adjustment, exactly as the spec asks -- **no new state
stored anywhere**: `_draw_body` gained a `night` flag and, when true, blends
`BODY_COLOR`/`BODY_HIGHLIGHT` 45% toward a cooler "moonlit" blue-grey
(`_blend_color`, a small linear RGB interpolation helper) before building
its existing gradient. Only the body's base color shifts, matching the
spec's literal wording -- ears/tail were deliberately left their normal
coral, a minimal-scope choice rather than chasing a fully "moonlit" cat
nobody asked for.

**Where each new input comes from, and why they're sourced differently**:
`accessory` is *pushed* into `window.py` via a new `set_accessory()` setter
(same no-op-if-unchanged pattern as `set_badge`/`set_streak`), recomputed
every 5-second `_on_tick` in `main.py` (`_apply_accessory`) since it
depends on `date.today()` and the stored `birthday`, neither of which
`window.py` has access to. `night`, by contrast, is computed *live inside
`paintEvent` itself* (`is_night_time(datetime.now().hour)`) with no setter
and no stored `self._night` field at all -- window.py already imports
`seasons.is_night_time` directly, so there was no reason to add a second
state-pushing pathway for something that's cheap to compute fresh on every
paint and, per the spec, explicitly shouldn't be new state.

**Feature 6 and 7's tray entries were built together**, per the spec's own
suggestion ("both are simple one-time `QSettings`-backed prompts -- natural
to build together"): "Set my birthday..." sits right below "Rename..." in
the tray menu, and birthday is loaded/stored the same way
(`self.settings.value("cat/birthday")`, an ISO date string).

**A real API mismatch caught during testing, not assumed away**: the spec
suggested "`A QInputDialog date entry is fine`", but this Qt binding's
`QInputDialog` has no `getDate` method at all -- confirmed by checking
`dir(QInputDialog)` rather than trusting the assumption, which returned
only `getText`/`getInt`/`getDouble`/`getItem`/`getMultiLineText`. First
attempt at the end-to-end check hit `AttributeError: <class
'PySide6.QtWidgets.QInputDialog'> does not have the attribute 'getDate'`
immediately. Fixed by using `QInputDialog.getText` with a `YYYY-MM-DD`
prompt instead, parsed via `date.fromisoformat` inside a `try/except
ValueError` that shows a `QMessageBox.warning` (the same invalid-input
pattern `_prompt_choose_repo` already uses for a non-repo folder) rather
than crashing or silently accepting garbage.

**Testing**: `pytest -q` -> **114/114 passed** (104 pre-existing + 10 new
`test_seasons.py` tests: Halloween, Yalda, an ordinary day with/without a
birthday set, a birthday matching regardless of birth year, both fixed
holidays correctly outranking a same-day birthday, and the night-time
range's interior hours plus its exact boundaries at 22/23/6/7). Rendered
every accessory value, `night=True`/`False`, and combinations with
streak/badge/hovering off-screen to confirm none throw; unit-verified
`_blend_color` at factors 0.0/0.5/1.0 directly; and rendered day-vs-night
twice and diffed the images (3,088 differing pixels) to confirm `night`
genuinely changes the rendered output, not just accepts the flag silently.
End-to-end against a real `GittenApp`: set a birthday via a patched
`QInputDialog.getText` and confirmed it persisted to `QSettings`,
confirmed `_apply_accessory()` correctly reflects whatever
`seasonal_accessory(date.today(), birthday)` returns for the real current
date, confirmed a birthday-matching date correctly threads all the way to
`window._accessory == "birthday"`, confirmed a cancelled dialog leaves the
birthday unchanged, and confirmed an invalid date string warns via
`QMessageBox` without crashing and without corrupting the previously-set
birthday.

With this, all 7 v1.5 features are implemented, tested, and documented.

## 14. v1.5 bug fixes from manual visual verification

After all 7 features landed, a manual pass over the live app (not just the
off-screen renders each feature's own testing section describes) turned up
three real bugs. This work spanned two sessions -- the first session found
all three bugs and ran out of context before fixing any of them (no code
was changed and nothing was committed, confirmed at the start of this
second session via `git status`/`git diff` coming back clean and this file
having no record of the three bugs beyond what's written here); this
section documents the investigation and fix for all three, done in the
second session.

### Bug A: drag sparkle trail jumping instead of trailing smoothly

**Root cause**: `_maybe_spawn_drag_particle` (Feature 2) spawned each
particle at `event.position()` -- coordinates *local to the widget*. But
the widget itself moves on every drag frame (`self.move(new_pos)` runs
before the spawn call), and the mouse's position relative to the widget
stays roughly constant throughout a drag (the drag offset is preserved).
So every spawned particle landed at nearly the same local coordinate, and
`paintEvent` drew each one at that fixed local coordinate on every
subsequent frame regardless of where the widget had since moved to. The
practical effect: sparkles didn't lag behind in screen space at all --
they rode along rigidly at the same spot relative to the cat, so a fast
drag (large per-frame position deltas) looked like the sparkles were
snapping/jumping along with the widget instead of leaving a smooth trail
behind it.

**Fix**: particles are now tracked in *global* (screen) coordinates instead
of widget-local ones -- `_maybe_spawn_drag_particle` spawns using
`event.globalPosition()`, and `trigger_shooting_star()` (Feature 3, reusing
the same particle system) converts its local corner-to-corner path to
global via `self.mapToGlobal(QPoint(0, 0))` as the origin, so its own
behavior is unaffected (the window doesn't move during a shooting star, so
the global/local distinction is a no-op for it). `paintEvent` converts back
to local coordinates at draw time (`global - self.mapToGlobal(QPoint(0,
0))`) before calling `draw_particles`. This means a sparkle now stays fixed
at the screen position it was spawned at while the widget moves away from
it, which is what actually makes it read as trailing behind rather than
being glued to the cat.

**Testing**: verified against a real, live `KittenWindow` instance (not
off-screen rendering, not reasoning about the diff): pressed the left
button to start a real drag, then fed 5 synthetic `mouseMoveEvent`s at
increasing global x-coordinates (with `time.monotonic` patched for
deterministic throttle timing) while moving the widget along with each one,
exactly mirroring what a real drag does. Confirmed all 5 particles spawned
(the throttle correctly let each one through), then computed the oldest
surviving particle's *current* local coordinate the same way the fixed
`paintEvent` now does and confirmed it had drifted to a negative local x
(off to the left of the widget) after the widget moved 80px to the right
without it -- concrete proof the sparkle is now trailing behind in screen
space rather than remaining glued to its original +60 local offset (which
is what the old, buggy code would have kept it pinned to forever).

### Bug B: hover-purr needed a ~0.2s hold delay

**Root cause**: `enterEvent`/`leaveEvent` (Feature 4) set `self._hovering`
immediately on entering the widget's region, so a single frame of the mouse
merely passing over the cat on its way elsewhere would trigger the purr
face, which read as twitchy rather than deliberate.

**Fix**: added `_HOVER_PURR_DELAY_MS = 200` and a single-shot
`self._hover_purr_timer`. `enterEvent` now starts that timer instead of
setting `_hovering` directly; only once it actually elapses
(`_on_hover_purr_delay_elapsed`) does `_hovering` flip to `True`.
`leaveEvent` stops the timer and clears `_hovering` immediately -- no delay
on the way out, since there's no equivalent "accidental blip" concern for
leaving, and an instant end to the purr reads better than a lingering one.

**Testing**: against a real, live `KittenWindow` with a real Qt event loop
(`app.processEvents()` pumped across real wall-clock time via
`time.monotonic()`, since this timer -- unlike the mood/attention/particle
timestamps elsewhere in this codebase -- is a genuine `QTimer` tied to real
elapsed time, not an injectable fake clock): confirmed `_hovering` is still
`False` and the pending timer is active ~120ms after `enterEvent`, confirmed
it flips to `True` by ~300ms, confirmed `leaveEvent` clears it and stops the
timer instantly, and separately confirmed a brief pass-over shorter than
the delay (enter, wait 50ms, leave) never triggers `_hovering` at all.

### Bug C: right-clicking the cat showed a stripped-down menu that looked like the tray's

**What manual testing actually saw** doesn't match what the wiring code
does: `KittenWindow.mousePressEvent` correctly calls
`self._context_menu_requested_callback`, which `main.py` sets to
`GittenApp._show_context_menu` (the full stats-menu builder) -- confirmed
directly, not assumed, by patching `GittenApp._show_context_menu` with a
spy *before* constructing a real `GittenApp`, dispatching a real synthetic
right-click `QMouseEvent` through the live window's actual
`mousePressEvent`, and confirming the spy fires exactly once with the
correct global position. The tray's own menu was never in this call path at
all.

**The real bug was one level deeper**: `_show_context_menu` (and, separately,
`_build_tray`) built each `QAction` as a bare local variable --
`QAction("some text")` with no parent -- and added it via
`menu.addAction(action)`. In PySide6, that call does **not** reparent or
otherwise take ownership of the action the way it might look like it
should from the C++ Qt docs; with nothing else holding a Python reference,
each action is garbage-collected the instant its local variable goes out of
scope (immediately, for the loop variable building the stats lines -- each
iteration's `info_action` is collected as soon as the next one is
assigned), silently vanishing from the menu before `menu.exec()` is ever
reached. Confirmed directly with a minimal repro (`QAction('x')` added to a
`QMenu()` with no other reference, `gc.collect()`, then `menu.actions()`
comes back empty; the same thing with `QAction('x', menu)` -- an explicit
parent -- correctly survives). Applied against the real `_build_tray()`
code before any fix: only `self.repo_action` (kept alive as an instance
attribute) and the separator (which never gets a Python-side `QAction`
wrapper in the first place) survived in the tray's own menu -- `Rename...`,
`Set my birthday...`, and `Quit Gitten` were all silently gone from
`menu.actions()`. This is almost certainly what manual testing actually
saw and described as "the tray's 2-item menu": not the tray's menu being
shown by mistake, but the *cat's own* freshly-built stats menu having lost
most of its unparented local actions to the same bug, leaving behind
something small enough to look like it.

**Fix**: every `QAction` constructed in `_build_tray` and
`_show_context_menu` now passes `menu` as its parent at construction
(`QAction("text", menu)`) instead of relying on `menu.addAction()` to keep
it alive. This gives Qt's own C++ parent/child ownership the job, so it no
longer depends on some other Python reference happening to still be in
scope.

**Testing, deliberately avoiding a known trap**: v1.5 Feature 6's own notes
(section 13) already flag that monkeypatching a compiled Shiboken method
like `QMenu.exec` silently corrupts `.actions()` on a menu built inside the
same patch context -- confirmed that's still true here (a first attempt at
patching `QMenu.exec` at the class level, to avoid the real blocking popup,
made this test script hang indefinitely and leave two stray `python.exe`
processes behind, which were killed manually). So instead of touching
`QMenu.exec` at all: (1) rebuilt the tray by constructing a real `GittenApp`
and reading `self.tray.contextMenu().actions()` directly after a
`gc.collect()` -- before the fix this returned only `Choose watched
repo...` plus the separator; after the fix, all 4 real actions
(`Choose watched repo...`, `Rename...`, `Set my birthday...`, `Quit
Gitten`) are present. (2) For the stats menu (whose real construction ends
in a genuinely blocking `menu.exec()` that can't safely be called from a
script), replicated `_show_context_menu`'s exact action-construction
statements verbatim, stopping right before the equivalent of `exec()`, and
confirmed all 9 expected actions (6 info lines + separator + "Change
watched repo..." + "Quit Gitten") survive a `gc.collect()` at that point --
none silently missing the way `Rename...`/`Set my birthday...`/`Quit
Gitten` were from the tray menu before the fix.

`pytest -q` was re-run after all three fixes: still **114/114 passed**
(none of the three bugs had pure-logic-module coverage to begin with --
they're all Qt-wiring/lifecycle issues in `window.py` and `main.py`, tested
the same ad hoc real-widget way this project's other Qt-only changes
already are, per the working agreement below).

## 15. Housekeeping: README overhaul

Input was `GITTEN_README_UPDATE_BRIEF.md`. The README had only ever
documented v1 and v1.1 -- everything from v1.2 onward (notification inbox,
sulking/reconciliation, streak, focus mode, the verified low-battery +
uncommitted-changes combo, one-liners + the rare shooting star, hover purr,
double-click high-five, drag sparkle trail, nameable cat, seasonal
accessories, day/night palette) was undocumented for anyone browsing the
repo, and the v1.5 bug-fix session (section 14) meant a couple of behaviors
(the drag trail's actual trailing mechanics, the hover-purr delay) needed
describing as they now actually work, not as originally specced. Per the
brief's own instruction, this file was read in full before writing a word
of the new README, rather than reconstructing behavior from memory of the
six spec files (which the notes above already show diverged from the
shipped behavior in several places -- e.g. `QInputDialog.getDate` not
existing, the tray-menu `QAction` garbage-collection bug).

**Rewrote README.md end to end**, organized per the brief's section list:
a features list grouped by category (git awareness / system awareness /
focus & productivity / notifications / personality & interaction /
personalization) instead of the old flat v1/v1.1-only structure; a
"How it's built" paragraph surfacing the independent-overlay-layers
architecture (mood / status badges / distraction-focus / attention-sulking
/ seasons all knowing nothing about each other, which is what lets several
of them show at once without special-casing) -- previously this was only
implicit across several dev-notes sections, never stated as a single
principle for a reader of the code; a configuration table mapping every
customizable behavior to where it actually lives (tray prompts +
`QSettings` vs. the three `~/.gitten/*.json` files, with their real default
values); and a **regenerated** (not hand-edited) project-structure tree,
built by actually listing `src/gitten/`, `tests/`, and `scripts/` on disk
rather than editing the previous tree, since the brief specifically flagged
that section as having gone stale after past feature rounds (confirmed true
-- the old tree was still missing `focus.py`, `streak.py`, `particles.py`,
`seasons.py`, and `oneliners.py`).

**Roadmap rewritten accurately rather than left as the old v1-only list**:
checked every spec file's own "explicitly deferred" section plus this
file's record of what actually shipped, rather than assuming. Confirmed via
grep that v1.3's actual taskbar-chase/favorite-vs-bad reactions were never
wired into `main.py` (only the standalone connection script and
`telegram_config.py` exist, per section 10) -- the roadmap now states this
as "in progress, blocked on the user's own Telegram API credentials"
instead of listing it as an unstarted future idea. Also carried forward
from the specs' own deferred sections: pass/fail-aware test/build
reactions, a full settings UI, live notification updates via WinRT's
`NotificationChanged` (GITTEN_V1_2_SPEC.md's own "nice-to-have, not
required" line), GitHub Actions/CI reactions, and decay during an
interrupted reconciliation (attention.py's own no-decay-while-partial
design, noted in section 9 as a "deliberate v1.2 simplification" that's
still true).

**Screenshot**: left the existing `assets/preview.png` (the v1 three-mood
off-screen render) in place rather than removing it, but added an explicit
`<!-- TODO: replace with real screenshot -->`-style HTML comment above it
per the brief's own fallback instruction -- this session has no working
screenshot/screen-recording tooling for the live desktop app (same
limitation recorded in section 4: this environment's GDI-based screen
capture of a layered/topmost window doesn't reliably show the real window
contents, and no `pyautogui`/`mss`/`pywinauto`-style tooling is installed),
so capturing a new live screenshot wasn't attempted rather than faked.

**Version bump**: `pyproject.toml` was still at `0.1.0` (not `0.2.0` as the
brief's phrasing assumed -- checked the file directly rather than trusting
that detail) despite v1 through v1.5 having shipped under it without ever
being bumped. Bumped to `0.6.0`, mapping each major version round to one
minor-version step (v1 -> 0.1, v1.1 -> 0.2, v1.2 -> 0.3, v1.3 (partial) ->
0.4, v1.4 -> 0.5, v1.5 -> 0.6) as a reasonable, defensible scheme given the
brief's "use your judgment" instruction, rather than an arbitrary jump.

**Also added `GITTEN_README_UPDATE_BRIEF.md` to version control**, same as
every other spec/brief file in this repo (see section 11 for the same
treatment of `GITTEN_V1_4_SPEC.md`).

Committed separately from any code change, per the brief's explicit
instruction, and pushed to `origin/main`.

## 16. v1.6 -- curiosity reaction on new app launch

Input is `GITTEN_V1_6_SPEC.md`. One feature: react when the user opens a
genuinely new program, defined precisely by the spec as a new process that
owns a visible, titled top-level window -- not every OS process (Windows
constantly spawns invisible background/helper processes) and not a new
window/tab inside an already-running app (no new process in the tracked
sense).

### `visible_windows.py` -- the win32 I/O boundary

New thin wrapper, same discipline as `foreground_window.py`: `win32gui.
EnumWindows` visits every top-level window, keeping only those that pass
both `IsWindowVisible` and a non-empty `GetWindowText`, resolves each to its
owning PID via `win32process.GetWindowThreadProcessId` (the same call
`foreground_window.py` already uses), and returns the set of distinct PIDs
with `os.getpid()` (Gitten's own process) excluded so it can never react to
itself. Guarded by the same top-level `try/except ImportError` pattern as
every other win32-touching module, returning an empty set on non-Windows.

### `app_launch.py` -- the pure decision, and the first-poll baseline case

`should_react_to_new_launch(previous_pids, current_pids, last_reaction_at,
now, cooldown=10.0)` follows the exact discipline every pure module in this
project uses: no Qt, no win32, the clock and PID sets all passed in by the
caller. A reaction is due when `current_pids - previous_pids` is non-empty
**and** the cooldown since the last reaction has elapsed (or there's never
been one) -- the cooldown exists so starting up a whole workspace at once
doesn't fire once per program.

**The first-poll baseline case, called out explicitly by the task**: an
empty `previous_pids` is treated as "no baseline established yet" and
always returns `False`, regardless of how many PIDs are in `current_pids`.
Without this, the very first poll after startup would see every already-
running program on the user's machine as a simultaneous new launch and
fire (at minimum) one reaction immediately -- exactly the noisy, wrong
behavior the spec warned against. `main.py` seeds `self._known_window_pids
= set()` at construction and simply always records whatever
`get_visible_window_pids()` returns after each check (whether or not it
reacted), so the *second* poll onward has a real baseline to diff against.
Verified both as a unit test (`test_empty_previous_set_on_first_poll_does_
not_react`, asserting `False` even with 5 fabricated "already open" PIDs
against an empty previous set) and live (see Testing below): a real
`GittenApp`'s first `_check_app_launch()` call, on this actual development
machine with its actual ~10 real visible windows already open, produced no
reaction at all -- not a synthetic scenario, the real desktop state.

### Reaction: a head-tilt, not just perked ears

The spec was explicit that "curious" needed to be genuinely distinguishable
from the existing `focused` (test/build) overlay side by side, not a near-
duplicate, even though both call for perked ears. The distinguishing touch:
a `_head_tilt` context manager (new in `sprite.py`) rotates the painter
around the head's own center (`center`, not the canvas origin) for exactly
the ears + face drawing calls, leaving the body/tail undisturbed -- so the
head visibly cocks to one side while the body stays put, reading as
"noticing something new" rather than "watching intently." `_draw_curious_
face` also differs from `_draw_focused_face` on its own merits, not just
the tilt: eyes with pupils held steadily off to one side (looking at
whatever just appeared) instead of `focused`'s fixed-dead-ahead pulsing
pupils, and a small round open "o" mouth instead of `focused`'s flat line
-- distinct from `WAITING`'s side-to-side glancing and wavy worried mouth
too. `trigger_curiosity()` (`window.py`) is the same "boolean flag +
`QTimer.singleShot` to clear it" idiom as `_trigger_high_five`, self-
clearing after 2 seconds per the spec.

**Precedence, decided and verified concretely rather than just reasoned
about, per the spec's explicit instruction**: sulking and the inbox view
suppress curiosity entirely, same as every other overlay (`turn_stage is
None`, and `view_mode == "pet"` already guaranteed by `window.py`'s
early-return in `paintEvent`, exactly as documented for `show_purr`/
`show_focused` in v1.5). Between the three standalone reactions: hovering
still wins over everything (a hand on the cat right now is the most
immediate signal, matching the existing v1.5 hover-vs-focused precedent),
and **curious wins over focused** -- reasoning: curiosity is a discrete,
momentary, self-clearing event (2s) representing something genuinely new
just happening, while focused is a passive, potentially long-running
"something's already in progress" state; a fresh surprise reads as more
attention-grabbing than continuing to watch an already-running test.
Verified with a pixel-diff, not just reasoning: `curious+focused` renders
**identically** (0 differing pixels) to `curious`-alone and differs from
`focused`-alone (2,067 differing pixels); `curious+hovering` renders
identically to `hovering`-alone (0 differing pixels) and differs from
`curious`-alone (1,845 differing pixels), confirming hover wins over
curious; `curious+turn_stage=1` renders identically to `turn_stage=1`-alone
(0 differing pixels), confirming sulking fully suppresses it.

### Wiring: reused the existing system-status timer, per the spec

`main.py`'s `_on_system_tick` (already firing every `SYSTEM_SAMPLE_
INTERVAL_MS` = 7s for the battery/CPU/disk badge) now also calls a new
`_check_app_launch()` -- no new `QTimer`, per the spec's explicit "poll on
the existing ~5-10s system-status timer rather than adding a new one."
`_check_app_launch` calls `get_visible_window_pids()`, feeds it and
`self._known_window_pids`/`self._last_curiosity_reaction_at` through
`should_react_to_new_launch`, calls `self.window.trigger_curiosity()` if
it's `True`, and unconditionally updates `self._known_window_pids` to the
current snapshot regardless of whether it reacted.

### Testing

`pytest -q` -> **122/122 passed** (114 pre-existing + 8 new
`test_app_launch.py` tests: no new PIDs, PIDs disappearing, a new PID
within cooldown, a new PID after cooldown, a new PID with no prior reaction
at all, the cooldown boundary being inclusive of exactly-elapsed, the
first-poll empty-baseline case described above, and the default cooldown
constant).

**Live, not just off-screen, per the task's explicit instruction** -- and
this session had a real interactive desktop available (confirmed early on:
`tasklist` showed two real, already-running `python -m gitten.main`
processes on this machine, left over from the user's own prior use rather
than anything this session started -- left untouched rather than killed,
since they weren't this session's to clean up):

1. Called the real `get_visible_window_pids()` for a baseline, then
   launched a real `notepad.exe` subprocess and polled until its actual PID
   appeared in the enumeration (it did, within a second) -- confirmed with
   `should_react_to_new_launch` that this real transition would trigger a
   reaction. Terminated the notepad process afterward.
2. Confirmed self-exclusion for real: created a real, visible, titled
   `QWidget` from inside the test's own process and confirmed `os.getpid()`
   never appears in `get_visible_window_pids()`'s result even though that
   window is genuinely visible and titled -- proving the exclusion isn't
   just a no-op because Gitten's own real window (borderless, no title)
   happens to already fail the title check.
3. Built a real, fully-wired `GittenApp` (`QT_QPA_PLATFORM=offscreen` for
   the Qt side, but every win32 call for real) and called
   `_check_app_launch()` for the first time on this actual machine's actual
   ~10-11 already-open real windows -- confirmed zero reaction (the
   first-poll baseline case, proven against real desktop state, not a
   fabricated PID set).
4. Launched another real `notepad.exe` after that baseline was established
   and polled the same live `GittenApp._check_app_launch()` -- confirmed
   `window._curious` flips to `True`.
5. Launched a third real `notepad.exe` one second later and confirmed the
   10-second cooldown correctly suppressed a second reaction
   (`_last_curiosity_reaction_at` unchanged).
6. Let real wall-clock time pass with `app.processEvents()` pumped (the
   same technique used to verify v1.5's hover-purr delay, since this is a
   genuine `QTimer` tied to real elapsed time, not an injectable fake
   clock) and confirmed `window._curious` self-clears back to `False`
   after ~2 seconds.

All spawned `notepad.exe` processes were terminated by the test script
itself; confirmed via `tasklist` afterward that no stray notepad or Python
processes were left behind beyond the two pre-existing ones noted above.

## 17. Housekeeping: richer demo image

`assets/preview.png` (the v1 three-mood contact sheet) was the only image
in the README, and per the housekeeping note in section 15, README.md had
carried a `<!-- TODO: replace with real screenshot -->` comment above it
ever since the v1.2-v1.5 README overhaul, since this environment has no
live-desktop screenshot tooling. Rather than a real screen capture, this
session generated a new, richer contact sheet the same way `preview.png`
was originally made: calling `paint_kitten` directly onto an off-screen
`QPixmap` for each state, then compositing them into one grid image with
labels -- no live screen capture involved, so the same environment
limitation that ruled out a real screenshot doesn't apply here at all.

**Six panels**, chosen to show off states from multiple features/versions
at once rather than just the original three moods: `HAPPY` mood with a low
battery badge (v1 mood + v1.1 badge, independent layers), a 30-day streak
crown (v1.4), a birthday party hat (v1.5), the hover-purr face (v1.5), the
fully-turned-away sulking pose (v1.2), and the new head-tilted curious
reaction (v1.6, this session's own prior feature).

**A real bug caught while building this, not just cosmetic tuning**:
generating the first pass with `QT_QPA_PLATFORM=offscreen` (this project's
usual headless-testing convention) produced every label and every
`drawText`-based sprite element (the "zzz" idle-mood glyphs) as tofu-box
placeholders -- the exact "offscreen platform has zero installed fonts"
issue already recorded in section 12 (v1.4 Feature 3) for the "!" vs "‼"
glyph swap. That limitation applies to *any* text rendered under the
offscreen platform, not just that one glyph comparison, and hadn't been hit
by an actual generated-asset workflow before now. Fixed by generating this
image with Qt's real default `windows` platform plugin instead (simply not
setting `QT_QPA_PLATFORM=offscreen`) -- this session has a real interactive
Windows desktop available (see section 16's testing), so the real platform
plugin's font database resolved correctly with no visible window ever
shown, since the script only ever paints onto an in-memory `QPixmap`. Also
adjusted two panel choices after visually reviewing the first render: the
streak panel's mood was changed from `IDLE` to `HAPPY` (idle's "zzz" glyphs
cluttered the crown), and the sulking panel was changed from `turn_stage=2`
to `turn_stage=0` (stage 2's partial face-reveal is real but too subtle to
read at this thumbnail size -- stage 0's fully-turned-back pose is
instantly readable as "sulking" even small).

Saved as `assets/demo.png` (688x538, 6 panels in a 3x2 grid). `README.md`'s
top image now references it, with the `<!-- TODO -->` comment removed --
the old `assets/preview.png` file itself was left in place rather than
deleted, since nothing in this task asked for that and it's still a
harmless part of the repo's history. Committed separately from any code
change and pushed to `origin/main`.

## 18. v1.7 -- mouse chase minigame

Input is `GITTEN_V1_7_SPEC.md`, the biggest feature to date: the cat moves
autonomously across the screen and a second small entity (a mouse) exists
elsewhere on screen at the same time. The spec explicitly called for
building and verifying each part in isolation before wiring them together,
and this section is written in that same order as the work actually
happened, not collapsed after the fact.

### Part 1: Autonomous walk (`window.py`), built and verified alone first

`walk_to(target_x, target_y, on_arrived=None)` records a target point and
sets a `_walking` flag; the actual per-frame movement is stepped from
`_on_animation_tick` -- the existing ~30fps `QTimer` that already drives
breathing/tail-sway/particles was repurposed (it previously just called
`self.update()` directly; now it calls a new `_step_walk()` first) rather
than adding a second timer, exactly per the spec. `_step_walk` moves the
window `_WALK_STEP_PIXELS` (8px) toward the target each frame using
`math.hypot` for the remaining distance, and once within
`_WALK_ARRIVAL_THRESHOLD_PIXELS` (4px) snaps exactly to the integer target
coordinate and fires `on_arrived` exactly once (the callback reference is
cleared before invoking it, so it can never double-fire even if something
re-enters).

**Drag-wins rule**: `cancel_walk()` clears `_walking` and, if a walk was
actually in progress, emits a new `walk_cancelled` signal --
`mousePressEvent`'s left-button branch calls `cancel_walk()` before
starting the drag, so a real user drag always immediately interrupts an
autonomous walk. `walk_cancelled` (rather than reusing the existing
`interacted` signal, which fires on *any* press including right-clicks) is
deliberately scoped to "a walk that was actually cancelled," which is
exactly what v1.7 Part 4's mid-chase-drag handling needs to know about
without also having to filter out right-clicks itself.

**Tested live, in complete isolation, before Part 2 existed at all**: a
real `KittenWindow`, a real `QApplication` event loop pumped with
`app.processEvents()` over real elapsed time (not an injected fake clock --
there's nothing to inject here, `_step_walk` only cares about the window's
actual current `pos()`), confirming (1) `walk_to` genuinely converges frame
by frame to an exact target and `on_arrived` fires exactly once and never
again afterward; (2) a real synthetic left-button `mousePressEvent` sent
mid-walk (confirmed via a few real ticks having already moved it off its
start position) cancels the walk immediately, fires `walk_cancelled`
exactly once, and the window genuinely stops moving on subsequent ticks;
(3) a real right-button press does *not* cancel an in-progress walk (proof
that `walk_cancelled` is correctly scoped to drags, not "any interaction").
`pytest -q` re-run after this part: unchanged at **122/122 passed** (Qt
wiring only, no new pure-logic module yet).

### Part 2: A second small window for the mouse (`mouse_window.py`), built and verified alone next

New `MouseWindow(QWidget)` copies `KittenWindow`'s window-flag setup
verbatim (`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
Qt.WindowDoesNotAcceptFocus`, `Qt.WA_TranslucentBackground`,
`Qt.WA_ShowWithoutActivating`) per the spec's explicit "no new window-flag
research needed" instruction -- literally copied, not re-derived. It
carries none of `KittenWindow`'s interaction logic (no drag, no click
handling, no view modes, no context menu): just `show_at(x, y)` (move +
show) and its own small ~30fps `QTimer` purely so the sprite's gentle
breathing animation has a `t` to animate against, reusing the same idiom
`KittenWindow` already uses for its own animation clock.

**`paint_mouse` (`sprite.py`)**, alongside `paint_kitten`: a small gray
rodent in the same minimal QPainter-primitives style, drawn in its own
64x64 logical canvas (mirroring `paint_kitten`'s 128x128-canvas-plus-
scale-transform pattern) -- an oval body with the same gentle breathing
sine-wave idiom used everywhere else in this codebase, two small round
ears, two black dot eyes, and a thin curved tail (a `QPainterPath` cubic,
the same technique `_draw_tail` already uses for the kitten's own tail).
Exactly the four elements the spec asked for, nothing extra (no nose or
whiskers) -- a single gently-breathing pose is enough per the spec, no
separate animation states needed. Visually confirmed by rendering it
directly to a `QPixmap` and looking at it before wiring anything further.

**Tested live, on its own, before Part 3 existed**: a real `MouseWindow`
instance -- confirmed its `windowFlags()`/`testAttribute(...)` match a real
`KittenWindow`'s exactly (not just "close enough", an actual equality
check against a real instance of each), confirmed `show_at(x, y)`
genuinely moves and shows a real widget at that exact position
(`isVisible()` true, `pos()` exact), and called `.grab()` (a real render of
the live widget, the same "don't just trust an off-screen `paint_kitten`
call" standard this project has used since v1.5) to confirm `paint_mouse`
doesn't throw and actually paints real, non-transparent pixels (541 out of
2304 in the grabbed image). `pytest -q` re-run after this part: unchanged
at **122/122 passed** (still no new pure-logic module).

### Part 3: Spawn timing (`mouse_game.py`, pure logic)

Same discipline as every pure module in this project -- no Qt, no win32,
everything injected by the caller:

- `random_spawn_interval_seconds(rng=None, min_minutes=45, max_minutes=90)`
  -- the exact same shape as `oneliners.random_interval_seconds`, same
  45-90 minute range (the spec said "your call," and reusing the existing
  range this codebase already established for the other "occasional
  background thing happens" timer seemed more consistent than inventing a
  new number for no reason).
- `should_spawn_mouse(view_mode, is_sulking, is_chasing, is_dragging)` --
  the same shape as `oneliners.should_show_oneliner`, gated on the same
  "pet view, not sulking" conditions plus two new ones specific to this
  feature: not already mid-chase, and not while the user is actively
  dragging the cat (the spec's one genuinely new gating rule).
- `pick_spawn_position(screen_left, screen_top, screen_right,
  screen_bottom, cat_x, cat_y, rng=None, min_distance=150.0,
  max_attempts=20)` -- uniformly samples points inside the given rect and
  rejects any closer than `min_distance` to the cat's current position,
  retrying up to `max_attempts` times before giving up and returning the
  last sampled point anyway (bounded, so a pathologically small screen
  can't spin forever trying to satisfy an unsatisfiable distance
  constraint).

**Testing**: new `tests/test_mouse_game.py`, mirroring `test_oneliners.py`'s
shape -- **136/136 passed** (122 pre-existing + 14 new): interval bounds
held over 500 seeded draws, custom bounds respected, determinism given the
same seed, every `should_spawn_mouse` gating combination (shows when clear,
skips when sulking, skips when in the inbox view, skips when already
chasing, skips when dragging, skips when everything's true at once),
`pick_spawn_position` always returning a point inside the given rect across
500 seeded draws, always satisfying the default minimum distance across
another 500, respecting a custom minimum distance, the small-rect edge case
(a 10x10 rect asked for a point 10,000px away from the cat) still
terminating and returning a point inside the rect rather than looping
forever, and determinism given a seeded RNG. This part is pure logic with
no Qt/win32 involved at all, so pytest is the right and sufficient test
here -- no separate live check was needed (unlike Parts 1, 2, and 4).

### Part 4: Wiring it together (`main.py`)

A new standalone `available_geometry()` in `window.py` (the primary
screen's available geometry, excluding the taskbar) was pulled out of
`default_position()`'s existing screen-query logic *without changing
`default_position()` itself* -- so `main.py`'s new mouse-spawn code has
somewhere to get screen bounds from without duplicating that query or
risking any behavior change to code that already worked.

A new single-shot `_mouse_spawn_timer`, scheduled and rescheduled exactly
like the existing `_oneliner_timer` (`_schedule_next_mouse_spawn` /
`_on_mouse_spawn_timer`, same "always reschedule regardless of whether this
occurrence actually did anything" pattern, and deliberately its own
independent timer/cadence rather than piggybacking on the one-liner timer,
since the spec called for "its own cadence"). On a poll that passes
`should_spawn_mouse`, `_start_mouse_chase()`: picks a spawn point via
`pick_spawn_position`, saves the cat's current position as
`self._chase_start_pos`, shows the mouse window there, and calls
`self.window.walk_to(mouse_x, mouse_y, on_arrived=self._on_mouse_caught)`.

`_on_mouse_caught` -- the "caught" callback -- hides the mouse window,
calls the new `window.trigger_catch_effect()` (a 10-particle burst radiating
outward from the cat's current center over 0.5s, reusing `ParticleSystem`
completely unchanged per the spec, same system already used for the drag
trail and shooting star -- particles tracked in global screen coordinates
and converted to local at paint time, same convention established for
those two features), clears the chase state, and walks back to the saved
pre-chase position with a second `walk_to` call (no `on_arrived` needed
this time -- arriving home doesn't need to trigger anything further).

**Mid-chase drag handling**: `main.py` connects `window.walk_cancelled` to
`_on_walk_cancelled`, which -- only if `self._is_chasing` is still true at
that moment -- hides the mouse window and clears the chase state
immediately, per the spec's explicit "don't leave it stranded on screen
with nothing chasing it" instruction. Because `_is_chasing` is set back to
`False` the moment the mouse is actually caught (before the return walk is
even issued), a drag that interrupts the *return* walk correctly does
nothing extra here -- there's no mouse window left to hide by that point,
and the cat simply stops wherever it was dragged, which is the same "drag
always wins, no exceptions" behavior every other autonomous animation in
this codebase already has.

### Testing (Part 4, full sequence, live)

`pytest -q` -> unchanged at **136/136 passed** (no new pure-logic module in
this part -- it's wiring on top of Parts 1-3).

**Live, end to end, against a real, fully-wired `GittenApp`** (bypassing
only the real 45-90 minute timer by calling `_start_mouse_chase()`
directly for a deterministic trigger -- everything downstream ran for
real, nothing else mocked):

- Confirmed the mouse window actually appears (`isVisible()`, exact spawned
  position) and the cat's real position genuinely converges toward it: sampled
  its distance to the mouse before and after 3 real animation frames and
  confirmed it measurably decreased (246.6px -> 222.5px in one run), not a
  teleport and not static.
- **A real timing subtlety worth recording**: the forward-arrival ->
  catch-effect -> return-walk-start chain all happens synchronously inside
  one `_step_walk()` call, so `is_walking` never observably reads `False`
  "at the mouse, before walking home" from outside the object -- by the
  time a poll loop sees it go `False`, the return walk has frequently
  *already finished too*. A first attempt at this test asserted the cat's
  position at "arrival" and failed because the round trip had already
  completed by the first check. Fixed by spying on `trigger_catch_effect`
  itself (an instance-level wrap of a plain Python method -- safe, unlike
  monkeypatching a compiled Qt/Shiboken method such as `QMenu.exec`, which
  this project's own v1.5 dev notes already flag as corrupting state) to
  observe exactly when it fires and how many particles exist at that exact
  instant (10, confirmed), regardless of how fast everything continues
  afterward.
- Confirmed the mouse window is hidden once caught, and that the cat
  genuinely walks itself all the way back to the exact position it was at
  before the chase started (polled to convergence, not just checked once).
- Triggered a fresh chase and sent a real synthetic left-button
  `mousePressEvent` mid-walk (confirmed several real frames had already
  elapsed first, so it was genuinely mid-walk, not still at the spawn
  moment): confirmed the walk stopped immediately, the mouse window was
  hidden right away rather than left stranded, and the chase state
  (`_is_chasing`, `_chase_start_pos`) was fully cleared.
- Confirmed a subsequent `_start_mouse_chase()` call right after that
  cancellation starts a completely normal new chase -- not stuck thinking
  one is still in progress, proving the cancellation path resets state
  completely rather than partially.

With this, all four parts of v1.7 are implemented, tested (unit tests for
the pure `mouse_game.py` logic; live, real-widget/real-event-loop testing
for every Qt-facing part, per the spec's explicit instruction not to trust
off-screen reasoning alone), and documented in the order they were
actually built.

## 19. v1.8 -- real keyboard/mouse idle detection

Input is `GITTEN_V1_8_SPEC.md`. This adds a second, independent "presence"
signal -- real system-wide keyboard/mouse inactivity via the Windows
`GetLastInputInfo` API -- distinct from the existing git-driven `idle`
*mood*, which only means "no git activity for a while" and says nothing
about whether anyone is actually sitting at the computer. The spec was
explicit that the real payoff here is the *suppression* wiring (three
already-built features going quiet while nobody's there to see them), not
just the new sleep pose, and this session treated it that way.

### `system_idle.py` -- the I/O boundary + the one pure decision

New module, same "thin wrapper, no decision logic" discipline as
`system_monitor.py` / `foreground_window.py`: `get_idle_seconds()` calls
`user32.GetLastInputInfo` via `ctypes` (no `pywin32` needed for this one --
it's not exposed there) to get the last-input tick count, and diffs it
against `kernel32.GetTickCount64()` -- **`GetTickCount64`, not the 32-bit
`GetTickCount`**, a deliberate choice to avoid the well-known ~49.7-day
wraparound bug the 32-bit counter has, even though it wasn't something the
spec called out explicitly. Returns `0.0` (i.e. "not idle") on any failure
rather than raising, matching every other win32-touching module's
degrade-gracefully discipline.

`is_away(idle_seconds, threshold_seconds=600.0) -> bool` lives in the same
file rather than a separate module the way `app_launch.py` is split from
`visible_windows.py` -- that split exists because `app_launch.py` grew real
branching logic worth isolating and testing on its own; `is_away` is a
single threshold comparison, so a second file would be pure overhead here.
It stays a plain binary gate (not graduated idle levels) per the spec's own
explicit steer, matching this codebase's other binary state gates (sulking,
focus), which have worked fine without more granularity.

### The AWAY "deep sleep" pose (`sprite.py`)

`paint_kitten` gained an additive `away: bool = False` parameter (default
unchanged, every existing call site unaffected, same pattern every prior
feature's new parameter has used). Distinguishing it concretely from the
existing git-driven IDLE pose, per the same bar v1.6 held itself to for
curious-vs-focused:

- **Body lies down instead of sitting** -- `_draw_body` gained a `lying`
  flag that widens the ellipse to 1.4x its normal horizontal radius and
  flattens it to 0.55x its normal vertical radius, instead of the regular
  upright oval. This is the single biggest visual differentiator and the
  main reason the pixel-diff below shows such a large count.
- **A slower, deeper breathing wave** -- a second sine (`away_breathe`, at
  `t * 0.7` with 0.05 amplitude) replaces the regular `t * 2.0` / 0.018
  breathing, per the spec's explicit "slower/deeper version of the existing
  breathing sine-wave" ask.
- **Ears droop** -- `_draw_ears` gained a `drooping` flag (height scaled to
  0.4x, leaning outward at 1.6x instead of the default 1.0x), the opposite
  extreme from the existing `perked` flag used by focus/curiosity.
- **Tail curls in** instead of swaying -- `_draw_tail` gained a `curled`
  flag that draws a small tucked loop near the body instead of the long
  swaying Bézier. Deliberately drawn *after* the (now much wider) lying
  body rather than before it, unlike the regular tail -- an early version
  drew it first and the wider body's footprint completely covered it, only
  caught by actually looking at a rendered image (see Testing below), not
  just the pixel-diff counts, which only prove *some* difference exists,
  not that it looks right.
- **A new `_draw_sleep_face`**: flat, straight closed-eye lines (distinct
  from IDLE's downward-curving light-doze eyes -- a curve reads as a
  relaxed blink, a flat line reads as properly shut) and a tiny closed
  mouth.
- **A bigger, slower zzz** -- `_draw_zzz` gained a `deep` flag: slower
  drift speed (0.28x vs 0.5x), taller rise (22px vs 16px), and larger
  letters (+3pt), positioned lower to sit over the flatter lying body
  instead of the taller sitting one.

### Precedence: AWAY fully overrides mood/reaction display

**Decided, not just assumed, per the spec's explicit instruction**: AWAY
sits above *every* other layer in the face/pose precedence chain (sulking,
purr, curious, focused, and the git-driven mood face itself) as a full
override, not another layer alongside them. Reasoning: the whole point of
this state is "nobody is here to see any of this" -- a sulking cat has no
one to perform sulking at, a purr/curious/focused reaction has no one to
perform for, and a fresh "!" or heart from the git mood is equally
pointless with no audience. Practically, none of those other reactions are
even reachable while genuinely away anyway (they all require live
mouse/keyboard input or a process check that v1.8's own suppression already
gates out), so the override mostly just guarantees consistency rather than
fighting anything.

**Verified concretely with a pixel-diff, the same standard held for v1.5's
purr-vs-focused and v1.6's curious-vs-focused decisions**, not left as
reasoning alone (`away vs idle`, `away+turn_stage` vs `away`-alone and vs
`turn_stage`-alone, `away+hovering`, `away+curious`, `away+focused`, and
`away` under `IDLE` vs `HAPPY` vs `WAITING` moods, all off-screen via
`QPixmap`):

```
away vs idle (should differ a LOT):                          5940
away+turn_stage vs away-alone (expect 0, full override):         0
away+turn_stage vs turn_stage-alone (expect >0, proves override): 5835
away+hovering vs away-alone (expect 0):                           0
away+hovering vs hovering-alone (expect >0):                   5799
away+curious vs away-alone (expect 0):                            0
away+curious vs curious-alone (expect >0):                     6723
away+focused vs away-alone (expect 0):                            0
away+focused vs focused-alone (expect >0):                     6434
away IDLE vs away HAPPY (expect 0, mood-independent):             0
away IDLE vs away WAITING (expect 0, mood-independent):           0
```

**A real bug this verification caught, not just a reasoning check that
passed**: the first version of the `away IDLE` vs `away WAITING` diff came
back non-zero (3353 differing pixels) instead of the expected 0. Cause:
`paint_kitten`'s existing `jitter_x` line (the WAITING mood's "nervous
shiver" horizontal jitter on the whole body) only checked `mood ==
Mood.WAITING`, with no `away` condition at all -- so a WAITING git mood
still made the *sleeping* cat visibly shiver, directly contradicting the
"mood-independent while away" precedence decision above and the spec's own
"deep-sleep regardless of whether the cat would otherwise be happy/
waiting/sulking" framing. Fixed with one added condition
(`and not away`); the diff above is from *after* that fix. Left as a
comment at the call site pointing back to this section, the same way the
v1.2 off-by-one bug and v1.6/v1.7 real bugs are documented at their fix
sites, so a future session doesn't have to rediscover the reasoning.

### Suppression -- the actually-useful part (per the spec's own framing)

Three existing gate functions each gained an additive `is_away: bool =
False` parameter, ANDed into their existing "AND together every condition"
shape exactly like every other condition they already check, per the
spec's explicit "add it the same way" instruction:

- `should_spawn_mouse` (`mouse_game.py`) -- spawning a chase minigame
  nobody is there to play is pointless.
- `should_show_oneliner` (`oneliners.py`) -- this is the single gate that
  already covered both the regular one-liner *and* the rare shooting-star
  roll (`_on_oneliner_timer` in `main.py` only rolls for the shooting star
  after `should_show_oneliner` already passed), so no second gate function
  was needed for "the rare shooting-star roll" the spec calls out
  separately -- it was already covered by construction.
- `should_react_to_new_launch` (`app_launch.py`, the v1.6 curiosity gate)
  -- reacting with curiosity to something new when nobody's there to notice
  is equally pointless.

### Wiring (`main.py`)

`_check_idle()`, a new method called from the existing `_on_system_tick`
(~7s system-status timer, per the spec's explicit "poll on the existing
timer, don't add a new one" instruction, the same timer v1.6's
`_check_app_launch` already piggybacks on) -- calls `get_idle_seconds()`,
computes `away_now = is_away(idle_seconds)`, and:

- On the *not-away -> away* transition, anchors `self._away_since = now -
  idle_seconds` -- **not** just `now` -- so the recorded absence start time
  is the real last-input moment, not merely "whenever this particular poll
  happened to run" (which could already be several minutes into the
  absence, given the 7s tick only checks periodically against a 10-minute
  threshold).
- On the *away -> not-away* transition, computes the real absence duration
  from that anchor and, if it's at least `WELCOME_BACK_THRESHOLD_SECONDS`
  (30 minutes, deliberately much longer than the 10-minute away threshold
  itself so a routine short break doesn't get greeted every time) **and**
  the cat is currently in the "pet" view (not the notification inbox),
  calls `self.window.show_nudge(WELCOME_BACK_MESSAGE)` -- reusing the
  existing nudge/one-liner bubble mechanism unchanged, per the spec's
  explicit "no new rendering needed" instruction.
- Always calls `self.window.set_away(away_now)` (new no-op-if-unchanged
  setter on `KittenWindow`, same pattern as `set_focused`/`set_badge`)
  regardless of whether a transition happened, so the sleep pose stays
  correct on every tick.

`self._is_away` (the `GittenApp`-level source of truth `_check_idle`
maintains) is threaded into all three suppression call sites:
`_check_app_launch`, `_on_oneliner_timer`, and `_on_mouse_spawn_timer` --
read directly from the instance attribute rather than back through
`window.py`, since `GittenApp` already computes and owns it authoritatively
each system tick (this does mean the mouse-spawn/one-liner timers, which
run on their own independent 45-90 minute cadences, see a value that can be
up to ~7 seconds stale relative to the system tick -- an acceptable,
already-established level of staleness in this codebase, the same kind the
distraction/focus timers' own independent cadences already have relative
to each other).

### Testing

`pytest -q` -> **146/146 passed** (136 pre-existing + 7 new
`test_system_idle.py` tests for `is_away` -- below/at/above the default and
a custom threshold, plus the default-constant value -- and one new test
added to each of `test_mouse_game.py`, `test_oneliners.py`, and
`test_app_launch.py` covering the new `is_away` suppression condition,
including an "everything going on at once, including away" combination
test in the first two, matching the existing style of those files rather
than only adding new isolated tests).

**Live, not just off-screen, per the task's explicit instruction**:

1. **The raw `GetLastInputInfo`/`GetTickCount64` call, confirmed genuinely
   live**: polled `get_idle_seconds()` every 1 second for 15 real seconds
   without touching the mouse/keyboard myself. Values came back jittery and
   sub-second (repeatedly resetting toward 0 rather than climbing smoothly)
   -- **this machine has continuous real background input activity during
   this session** (almost certainly the actual user's own concurrent use of
   the machine, since the pattern is irregular rather than a fixed-interval
   heartbeat), which made it impossible to observe a genuine 10-minute
   idle-to-AWAY transition through real, unassisted waiting in this
   session. This is recorded here as a real environment characteristic
   (same spirit as the v1.4 offscreen-fonts and v1 zombie-process notes),
   not swept under the rug -- what it *does* conclusively prove is that the
   wrapper is reading real, live, sub-second-granularity system state
   (correctly resetting in real time as real input actually happens),
   rather than a stub or a value that only changes with process uptime.
2. **The full transition + wiring, verified against a real, fully-wired
   `GittenApp`** (`QT_QPA_PLATFORM=offscreen` for the Qt side, everything
   else real, same convention as the v1.6/v1.7 live tests) by
   monkeypatching `gitten.main.get_idle_seconds` -- a plain Python function
   reference, not a compiled Qt/Shiboken method, so safe to monkeypatch per
   this project's own established caution (see the v1.5/v1.7 dev notes
   about `QMenu.exec` corrupting state) -- to simulate specific real idle
   values while every downstream step (`_check_idle`, `window.set_away`,
   the suppression gates, the welcome-back nudge) ran unmocked:
   - A simulated 650s idle value correctly flipped `self._is_away` and
     `window._away` to `True`, with `_away_since` anchored to within ~2ms
     of the real "absence actually started ~650s ago" expectation.
   - While away, `_on_oneliner_timer()` left `window._nudge_text`
     unchanged (no new nudge fired) and `_on_mouse_spawn_timer()` left
     `self._is_chasing` at `False` (no chase started).
   - **Curiosity suppression confirmed against a real process, not a
     fabricated PID set** -- mirroring the v1.6 live test exactly: launched
     a real `notepad.exe`, polled the real `get_visible_window_pids()`
     until its actual PID appeared (confirmed within ~1s), then called
     `_check_app_launch()` while `self._is_away` was `True` and confirmed
     `window._curious` stayed `False` despite the genuinely new process --
     proving the suppression actually blocks a real launch, not just a
     synthetic one. The notepad process was terminated afterward; `tasklist`
     confirmed no stray notepad processes were left running.
   - A short simulated absence (~20s, well under the 30-minute
     `WELCOME_BACK_THRESHOLD_SECONDS`) transitioning back to active
     correctly left the nudge bubble untouched (`None`).
   - A long simulated absence (~2000s, over the 30-minute threshold)
     transitioning back to active correctly set `window._nudge_text` to
     exactly `WELCOME_BACK_MESSAGE`.
3. **The AWAY pose rendered and visually inspected**, both via an
   off-screen `QPixmap` pixel-diff (see the precedence section above) and
   via a real side-by-side contact sheet (`paint_kitten` called directly
   with Qt's real `windows` platform plugin, not `offscreen`, for correctly
   rendered fonts -- the same font-rendering gotcha recorded in section 17
   -- with no window ever actually shown on screen, since it only paints
   onto an in-memory `QPixmap`) confirming the lying body, drooping ears,
   flat closed eyes, and bigger zzz genuinely read as "asleep" and
   genuinely read as different from the regular sitting IDLE pose next to
   it, not just different by pixel count.

With this, v1.8's detection, pose, precedence decision, and all three
suppression gates are implemented, tested, and documented.

## 20. v1.9 -- quick command bar

Input is `GITTEN_V1_9_SPEC.md`, a new text command bar summoned by a global
hotkey: type `streak`, `commits`, `battery`, `rename <name>`, `chase`,
`help`, or `quit` and get an immediate reply. Built in the exact order the
spec lays out -- parsing, then handlers, then the popup, then the hotkey --
testing each part on its own before wiring it into the next, the same
discipline v1.7's four-part build already established. Every Qt-facing
part (the popup, the handlers wired to a real app, and the global hotkey)
was verified **live** this session, not just reasoned about off-screen --
see Testing below for exactly what "live" meant for each part.

### Part 1: `commands.py` -- parsing + reply formatting

`parse_command(text: str) -> tuple[str, str]` is exactly what the spec
describes: lowercase and trim the whole input, then split on the first
whitespace into `(command, argument)`, with `argument` defaulting to `""`.
Zero Qt/git/psutil imports, following the same pure-function discipline as
every other `*.py` module with no I/O in this codebase (`mood.py`,
`streak.py`, `distraction.py`, ...).

**A deliberate, spec-driven tradeoff worth flagging explicitly**: because
the spec says to lowercase the *whole* input before splitting, `rename Bob`
parses to `("rename", "bob")` -- the argument gets lowercased too, so
`rename` can currently only ever produce an all-lowercase cat name via the
command bar (the tray's "Rename..." dialog is unaffected -- it never goes
through `parse_command` at all). This was implemented literally as
specced rather than special-cased, since the spec's wording was
unambiguous; flagged here in case a future session is asked to make it
case-preserving.

The rest of `commands.py` is a set of small pure formatting functions --
`format_streak_reply`, `format_commits_reply`, `format_battery_reply`,
`format_rename_reply`, `format_chase_reply`, plus the `COMMANDS_HELP_TEXT`
and `UNKNOWN_COMMAND_REPLY` constants -- that take already-gathered plain
values (an `int | None`, a `float | None`, a name string) and return the
exact reply text to show. This is the same split `notifications.py`
already established for `format_notification`: keep the "what text to
show" decision pure and testable, and leave the actual data-gathering
(git log calls, a `psutil.sensors_battery()` read, cat-rename persistence,
the mouse-chase trigger) as thin glue in `main.py`, the same place
`_stats_menu_lines` already blends I/O with formatting for the right-click
stats menu. This is also what the spec's "these handlers need access to
already-existing app state... so they can't be fully Qt-free" note was
pointing at -- the *decision* logic here is Qt-free and unit-tested; the
*wiring* to real app state isn't, and is verified live instead (see
Testing).

**Testing**: new `tests/test_commands.py`, 21 tests -- `parse_command`
(empty input, whitespace-only input, a bare command, trailing whitespace,
a command with an argument, extra internal whitespace collapsing correctly,
uppercase input lowercasing, and a multi-word argument staying joined) and
every formatter (value vs. `None`/empty-argument cases, plus the help text
mentioning every command name and the unknown-command reply mentioning
`help`). `pytest -q` -> **167/167 passed** (146 pre-existing + 21 new).

### Part 2: the command dispatch table

Lives as a method on `GittenApp` (`_dispatch_command(command, argument) ->
str | None`), per the spec's explicit "use your judgment... the same way
you've made similar plumbing calls before" -- this mirrors where
`_show_context_menu`/`_stats_menu_lines` already ended up: app-state-heavy
glue lives on `GittenApp` itself rather than a separate stateless module,
since it needs `self.watcher`, `self.window`, `self.settings`, and
`self._is_chasing` directly. It returns the reply text (formatted via
`commands.py`'s pure functions above) rather than calling
`window.show_nudge` itself, so it stays a plain, directly-callable method a
test can invoke and assert on without needing to also assert on the nudge
bubble's internal state. `_on_command_submitted` (the popup's signal
handler, wired in Part 3) is the only thing that actually calls
`window.show_nudge(reply)`, and only when `reply is not None` -- `quit` is
the one command that returns `None` and just calls `self.app.quit()`
instead, per the spec.

Each handler reuses an existing mechanism rather than duplicating it, per
the spec's explicit instructions for `streak`/`commits`/`chase`, and
extended to `rename` on the same principle:
- `streak` / `commits` call `get_commit_streak` / `count_commits_today`
  from `git_watcher.py` unchanged (the exact same functions the stats menu
  already uses), passing `None` through when no repo is watched (mirroring
  `_stats_menu_lines`' own "--" fallback).
- `battery` reads `psutil.sensors_battery()` directly, the same call
  `_stats_menu_lines` already makes.
- `rename <name>` required pulling the tray dialog's rename effect out into
  a new shared `_apply_rename(name: str)` method (settings persist +
  tooltip refresh) so `_prompt_rename` (the dialog) and the new command
  handler both call the same code instead of the command handler
  reimplementing it -- the same "extract the shared effect" pattern this
  session applied that the spec only asked for explicitly on `chase`.
- `chase` calls the existing `_start_mouse_chase()` directly, bypassing the
  random spawn timer entirely, exactly as specced. One small addition
  beyond the spec's letter: if a chase is already in progress,
  `_dispatch_command` doesn't start a second one on top of it (which would
  silently retarget the in-flight `walk_to` and leave two mouse-window
  states confused) -- it replies "already on the hunt!" instead, via
  `format_chase_reply(already_chasing=True)`.
- `help` returns the static `COMMANDS_HELP_TEXT`; `quit` calls `self.app.
  quit()`; anything else (including the empty-string command from empty
  input) falls through to `UNKNOWN_COMMAND_REPLY`, satisfying the spec's
  "never silently do nothing" for unrecognized input.

**Testing**: no pytest file for this part, matching this codebase's
existing convention that a full `GittenApp` is exercised live/headlessly
rather than unit-tested in isolation (no `test_main.py` has ever existed;
see the v1.2/v1.6/v1.7/v1.8 dev notes for the same pattern). Instead, a
scratch script instantiated a real `GittenApp` (`QT_QPA_PLATFORM=
offscreen`) pointed at a real scratch git repo (one real commit, made
today) and called `_dispatch_command` directly for every command,
confirming against real data: `streak` → `"Streak: 1 day(s)"`, `commits` →
`"Commits today: 1"`, `battery` → a real `"Battery: 78%"` reading from this
machine, `rename bob` → `app.cat_name` actually became `"bob"` and the
reply confirmed it, a second bare `rename` with no argument left the name
unchanged and replied with the usage hint, `chase` actually set
`_is_chasing = True` and made the real `mouse_window` visible, a second
immediate `chase` call while still chasing did *not* start a second one and
replied `"already on the hunt!"`, `help` listed every command name, both
`asdf` and empty input produced the unknown-command reply, and `quit`
(with `app.app.quit` swapped for a spy) called it exactly once and returned
`None`.

### Part 3: `command_bar_window.py` -- the popup

A `QWidget` subclass carrying one `QLineEdit`, reusing `KittenWindow`/
`MouseWindow`'s proven `FramelessWindowHint | WindowStaysOnTopHint | Tool`
+ `WA_TranslucentBackground` combination -- but **deliberately dropping**
`Qt.WindowDoesNotAcceptFocus` and `Qt.WA_ShowWithoutActivating`, the two
flags that make the *other* two windows never steal keyboard focus. This
window is the opposite case: it's a real text box, so it has to actually
receive focus to be usable, and it has to be able to detect *losing* focus
(a real `QEvent.FocusOut` on the line edit) to implement "clicking
elsewhere closes it." Escape is caught via an event filter installed on the
`QLineEdit` itself (checking for `QEvent.Type.KeyPress` +
`Qt.Key_Escape`) rather than overriding `keyPressEvent` on the window,
since the line edit is what actually holds focus and receives the key
event first.

The window doesn't parse or dispatch anything itself -- `command_submitted
(str)` just emits the raw typed text on Enter, after already hiding itself.
`main.py`'s `_on_command_submitted` is what calls `parse_command` +
`_dispatch_command`. This keeps the popup fully self-contained, per the
spec: it never touches `KittenWindow`'s `view_mode`/click-handling state
machine, the same "separate popup, not a mode of the existing window"
split `mouse_window.py` already established for the chase minigame's mouse
sprite.

`GittenApp._show_command_bar()` (the hotkey's callback, added in Part 4 but
tested here too) positions the bar just above the cat's current position,
horizontally centered on it, clamped into the primary screen's available
geometry via the same `available_geometry()` v1.7's mouse-spawn logic
already uses -- no new screen-geometry code.

**Testing -- live, not off-screen, per the spec's explicit instruction**:
a standalone script ran a real (non-offscreen) `QApplication` and used
`QTest.keyClicks`/`QTest.keyClick` (real synthetic Qt keyboard events
delivered through the real event system, not mocked signal calls) against
a real, shown `CommandBarWindow`:
- Typing `"streak"` then `Qt.Key_Return` fired `command_submitted` with
  exactly `"streak"` and left the bar hidden afterward.
- Typing `"commits"` then `Qt.Key_Escape` fired nothing and left the bar
  hidden -- confirming Escape genuinely discards instead of submitting.
- Showing the bar, then calling `setFocus` on a `QLineEdit` inside a
  second, separate real window (with `QTest.qWaitForWindowActive` given
  time to let the window manager actually switch active-window state)
  closed the bar with nothing emitted -- confirming real OS-level focus
  loss, not just an internal flag, triggers the close.

Then the full wiring was exercised against a real, fully-wired `GittenApp`
(real scratch repo again): called `_show_command_bar()` directly (Part 4's
hotkey wasn't built yet at this point in the build order), confirmed the
bar appeared near the cat's real on-screen position, typed `"streak"` via
`QTest` and pressed Enter, and confirmed the *real* nudge bubble
(`window._nudge_text`) ended up holding the real reply
(`"Streak: 1 day(s)"`) -- the whole popup-to-reply path running for real,
nothing mocked.

### Part 4: the global hotkey (`command_bar_hotkey.py`)

Registers Ctrl+Alt+G via the raw `user32.RegisterHotKey` Win32 API through
`ctypes` -- consistent with `system_idle.py`'s existing raw-ctypes style
for a win32 call `pywin32` doesn't expose, and per the spec's explicit "no
new third-party hotkey library" instruction. `RegisterHotKey` binds the
combination to a specific window handle's message queue; a
`QAbstractNativeEventFilter` subclass (`_HotkeyEventFilter`) is what
actually catches the resulting `WM_HOTKEY` message, since Qt calls every
installed native event filter for every native message it pumps through
the app's own event loop on that thread -- no second message loop, no
polling.

`register_global_hotkey(hwnd, callback)` **checks `RegisterHotKey`'s
return value and returns `None` on failure** (logging why -- e.g. another
app already owns Ctrl+Alt+G) rather than crashing or raising, exactly the
"check the return value, degrade gracefully" discipline the spec asked
for and every other win32-touching module in this codebase (`system_idle.
py`, `foreground_window.py`, `notifications.py`) already follows. `main.
py`'s `_register_command_bar_hotkey()` only calls `app.
installNativeEventFilter(...)` when registration actually succeeded, so a
failed registration leaves the rest of the app completely unaffected --
the command bar just becomes hotkey-less for that session (there's no
other way to summon it yet, since there's no tray-menu entry for it in
this spec -- worth adding in a future session as a fallback for exactly
this failure case). The hotkey is unregistered via `app.aboutToQuit`,
matching the pattern `git_watcher.py`'s `stop()` already sets for cleaning
up a live OS-level resource on shutdown.

The hardcoded `Ctrl+Alt+G` combination is called out with a `TODO` comment
in `command_bar_hotkey.py` pointing at "make this configurable once a
settings UI exists," per the spec's explicit instruction, since there's no
settings panel yet.

**Testing -- live, with a REAL simulated physical key press, per the
spec's explicit instruction not to trust an off-screen assumption**:
`RegisterHotKey`/`WM_HOTKEY` is a genuine OS-level, system-wide mechanism
that can't be exercised through Qt's own synthetic event system at all
(Qt's `QTest.keyClick` only ever delivers events to a specific widget, it
never goes through the real Windows message queue) -- so the only way to
actually prove this works is a real simulated hardware-level key press.
A standalone script called `user32.keybd_event` directly (`VK_CONTROL`,
`VK_MENU`, `VK_G` down, then up in reverse order -- wrapped in a
`try/finally` that always releases all three keys, so a failed assertion
mid-test can never leave Ctrl/Alt "stuck down" system-wide) against a real
registered hotkey and confirmed the callback actually fired. Also
confirmed: `unregister_global_hotkey` genuinely releases the combination
(a fresh `register_global_hotkey` call for the same hwnd succeeded cleanly
afterward, proving the first registration wasn't a no-op to begin with),
and registering the same combination on a second, different window handle
while the first still held it returned `None` instead of crashing (Windows
error 1409, `ERROR_HOTKEY_ALREADY_REGISTERED`, confirming the "another app
already owns it" failure path is real and correctly handled, not just
theoretical).

**Then the full v1.9 chain end to end, live, with nothing mocked
anywhere**: a real, fully-wired `GittenApp` (real scratch repo, real
window shown on screen), a real Ctrl+Alt+G physical key simulation via
`keybd_event` (not a Qt synthetic event -- this exercises the actual
registered OS hotkey path, proving `main.py`'s wiring and not just the
standalone module), confirmed the real command bar (`app.command_bar`)
actually became visible as a direct result, then typed `"commits"` via
`QTest.keyClicks` and pressed Enter, and confirmed the real nudge bubble
ended up holding the real reply (`"Commits today: 1"`, matching the one
real commit in the scratch repo) -- the entire hotkey → popup → parse →
dispatch → git-log-call → reply-bubble chain, run for real, once, start to
finish.

`pytest -q` re-run after all four parts -> unchanged at **167/167 passed**
(Parts 2-4 added no new pure-logic module, only Part 1 did). `tasklist`
was checked after every live script and confirmed no stray `python.exe`
processes were left running, avoiding a repeat of the v1's zombie-process
lesson (these scripts never call `app.exec()`, so the process exits
cleanly on its own once the script finishes).

With this, all four parts of v1.9 are implemented, tested (unit tests for
the pure `commands.py` logic; live, real-event/real-OS-API testing for the
dispatch wiring, the popup, and the global hotkey, per the spec's explicit
instruction not to trust an off-screen assumption for any of them), and
documented in the order they were actually built.

### Bugfix: the command bar was invisible

Reported after the session above: the popup worked functionally (Enter/
Escape/focus-loss, the real hotkey, real replies) but had **no visible
box on screen** -- just a bare `QLineEdit` floating with nothing behind it,
so there was nothing showing *where* to type.

**Root cause**: `CommandBarWindow.__init__` set a QSS stylesheet
(`background-color: rgba(...); border-radius: 8px;`) on the top-level
`QWidget` itself via `setObjectName` + `setStyleSheet`. This looked
identical in shape to how `window.py`'s inbox panel styles itself, but it
doesn't actually work the same way: **a plain `QWidget` never paints its
own stylesheet background/border unless `Qt.WA_StyledBackground` is also
set.** Widgets with a default `paintEvent` that consults the current style
(`QPushButton`, `QLabel`, `QFrame`, ...) get this for free; a bare
`QWidget` subclass with no custom `paintEvent` does not, and this one had
none -- so the rounded rect in the stylesheet was silently never
rendered, leaving `WA_TranslucentBackground` fully transparent everywhere
including where the "backdrop" was supposed to be. `pytest`/the earlier
live keyboard/focus tests never caught this because none of them checked
*pixels* -- they only asserted on signals, visibility flags, and text,
all of which were correct regardless of whether anything was actually
painted.

**Fix**: replaced the stylesheet-background approach with a `paintEvent`
override that draws the rounded backdrop directly with `QPainter`
(`QColor(32, 32, 36, 235)` fill, a lighter `QColor(110, 110, 118)` 1px
border, `_CORNER_RADIUS = 10`) -- the same "draw it yourself with
QPainter primitives on a translucent window" approach every other
transparent top-level widget in this codebase already uses successfully
(`sprite.py`'s `paint_kitten`, `MouseWindow`'s `paint_mouse`), rather than
leaning on QSS painting a plain `QWidget`'s background, which doesn't work
without the extra attribute. The `QLineEdit`'s own stylesheet stays (it's
a real `QLineEdit`, which *does* paint its own stylesheet correctly) but
switched to fully `background: transparent` so the backdrop underneath
shows through, plus an explicit `selection-background-color`/
`selection-color` for a clearly visible text-selection state against the
dark backdrop. The layout gained `_PADDING = 8` px of margin on all sides
(previously 0) so the backdrop visibly frames the input with breathing
room instead of being flush with its edges, per the bug report's "reasonable
padding" ask.

**Testing -- this time actually checking pixels, not just paintEvent
running, per the explicit instruction**: a live script ran a real,
fully-wired `GittenApp`, sent a real simulated physical Ctrl+Alt+G key
press (`user32.keybd_event`, the same technique as the v1.9 hotkey tests
above) to summon the popup through the real registered hotkey, typed
`"streak"` via real `QTest` keyboard events, then took a **real screen
grab** (`QScreen.grabWindow`, capturing actual composited desktop pixels,
not an off-screen `QPixmap` render) of the region the popup landed in and
saved it to a PNG.

- **The PNG was actually opened and visually inspected** (not just
  pixel-sampled) -- it clearly shows a rounded dark panel with a visible
  lighter border, sitting on top of the real desktop background (a dark
  wallpaper, with the kitten's sprite visibly peeking out just below the
  bar), with white "streak" text and a visible text cursor inside it. This
  is the direct confirmation the bug report specifically asked for:
  clearly visible against a normal desktop background.
- **A pixel-level regression check** was added on top of the visual
  inspection: sampled the composited color at the backdrop's center pixel
  and compared it to the exact color `paintEvent` was asked to paint
  (`32, 32, 36`) -- came back `(30, 31, 36)`, a difference of 3 total
  across all three channels (well within anti-aliasing/compositing
  rounding), confirming the intended paint operation is what's actually
  reaching the screen. **An earlier version of this same check used a
  "differs from a neighboring desktop pixel" heuristic instead and
  intermittently failed** even after the fix was visually confirmed
  correct -- because the particular desktop wallpaper corner it happened
  to sample was independently dark, making the diff too small to clear an
  arbitrary threshold. Replaced with the exact-color-match check above,
  which is what's recorded here; a lesson for any future pixel-based live
  check in this codebase: assert against the known intended color, not an
  assumption about what the surrounding desktop looks like.
- Re-ran the earlier Part 3 live keyboard/focus test (Enter submits +
  closes, Escape discards + closes, real OS focus-loss closes) unchanged
  after the fix -- still 3/3 passing, confirming the visual fix didn't
  regress any interaction behavior.
- `pytest -q` -> unchanged at **167/167 passed** (this was a pure
  rendering fix, no logic/test changes).

**A process-hygiene note from this session, not a code bug**: partway
through this fix's live testing, `RegisterHotKey` started failing with
Windows error 1409 (`ERROR_HOTKEY_ALREADY_REGISTERED`) even though no
test script *appeared* to still be running. `tasklist` found one leftover
`python.exe` still alive from an earlier live-test script in the previous
session -- one that had called `watcher.set_repo(...)` (starting a
`watchdog.Observer` thread, which isn't a daemon thread) but never called
`watcher.stop()` or unregistered its hotkey before the script's main flow
ended, so the interpreter never actually exited despite reaching the end
of the script. Killed the stray process (`taskkill`) to free the hotkey,
matching this exact same class of issue already recorded in section 4's
v1 "zombie processes" debugging story -- worth remembering for any future
live-test script in this project that calls `watcher.set_repo(...)`:
either call `watcher.stop()` at the end, or expect the process to hang
around afterward.

## 21. v1.10 -- reminders

Input is `GITTEN_V1_10_SPEC.md`, built directly on top of v1.9's command
bar: three new commands (`remind <duration> <message>`, `reminders`,
`cancel <id>`) added to the existing `_dispatch_command` table rather than
a parallel dispatch mechanism, per the spec's explicit "read
DEVELOPMENT_NOTES.md first, in full" and "extend the existing table, don't
parallel it" instructions -- both `GITTEN_V1_10_SPEC.md` and this whole
file were read in full before writing any code, not just the most recent
sections.

### `reminders.py` -- pure logic + the JSON persistence boundary

Same shape as every other pure module: a `Reminder` dataclass (`id`,
`message`, `due_at`, `created_at`), `parse_duration(text) -> (seconds |
None, remaining_text)` following `commands.parse_command`'s exact "pure
parsing returns a tuple" convention (a regex requiring the first
whitespace-separated token to be a number immediately followed by `s`/
`m`/`h`, no space inside the token, no other units), `due_reminders(
reminders, now) -> list[Reminder]` (`due_at <= now`, boundary inclusive),
`next_reminder_id`/`create_reminder`, and a set of `format_*` reply
functions mirroring `commands.py`'s existing formatter split (pure, take
plain values, return display text) -- kept in `reminders.py` itself rather
than moved into `commands.py`, the same way `notifications.format_notification`
lives with `NotificationItem` rather than in some shared generic-formatter
module. `load_reminders`/`save_reminders` (JSON, `~/.gitten/reminders.json`)
live in this same file rather than a separate one, matching
`distraction.py` (matching logic + `load_distraction_lists`) and
`telegram_config.py` (`load_config`/`save_config`)'s established "pure
decision + a small file-I/O boundary, same file" shape -- the spec's "no
file I/O in the core logic" instruction is about keeping *decision* logic
free of I/O, not a ban on I/O existing anywhere in the module, and this
codebase has never drawn that line as a separate file before.

**A clock choice worth being explicit about, since it's a real deviation
from this codebase's usual convention**: every other pure module
(`mood.py`, `attention.py`, `distraction.py`, ...) is fed `time.monotonic()`
by its caller. Reminders can't use that -- they're persisted to disk and
must still make sense after the app (or the machine) restarts, and
`time.monotonic()`'s zero point is arbitrary per-process and meaningless
across a restart. So every timestamp flowing through `reminders.py` is
real wall-clock time (`time.time()`), and `main.py` is careful to pass
`time.time()` everywhere it talks to this module, never `time.monotonic()`
-- documented directly in the module's own docstring so a future session
doesn't copy the wrong clock by habit from every other tracker in this
codebase.

**Id assignment recomputes from the current list** (`next_reminder_id =
max(existing ids, default=0) + 1`) rather than tracking a separate running
counter -- the same "recompute rather than track something that can drift"
idiom `streak.py`/`count_commits_today` already established, and it means
a cancelled reminder's id is never accidentally reused.

**Testing**: new `tests/test_reminders.py`, 41 tests -- `parse_duration`
(each unit, a decimal value, no message after the duration, a missing
unit, non-numeric text, an unsupported unit, a space inside the token,
empty input), `due_reminders` (none due, some due, the exact-boundary
case, an empty list), id assignment and `create_reminder`, every
formatter (including plural/singular phrasing for the flush reply and the
usage-hint constants), and a full save/load persistence round-trip plus
the missing-file/invalid-JSON/parent-directory-creation cases mirroring
`test_telegram_config.py`'s existing shape for those exact scenarios.
`pytest -q` -> **202/202 passed** (167 pre-existing + 35 new
`test_reminders.py` tests).

### Wiring: three new commands, plus updating `help`

`_dispatch_command` gained `remind`/`reminders`/`cancel` branches
following the exact pattern already established for `streak`/`commits`/
`chase`: thin glue here, the real decision in `reminders.py`.
`remind`/`cancel` needed slightly more glue than a one-liner (parsing,
validating, mutating `self.reminders`, persisting) so each got its own
small helper method (`_handle_remind_command`/`_handle_cancel_command`),
the same "extract when there's real logic, inline when it's one call"
judgment call already applied to `rename`'s `_apply_rename` extraction in
v1.9. Both malformed-input paths (`remind` with no duration, `remind 10m`
with no message, `cancel` with no id or an unknown id) return the
usage-hint reply rather than silently doing nothing, per the spec's
explicit callback to the existing "never silently do nothing" rule
(`rename` with no argument, any unrecognized command). `COMMANDS_HELP_TEXT`
(`commands.py`) now lists all three new commands alongside the existing
six.

`self.reminders = load_reminders(DEFAULT_REMINDERS_PATH)` is loaded once
at `GittenApp.__init__`, right next to the other tracker state; every
mutation (`remind`, a successful `cancel`, or a fire/flush) immediately
calls `save_reminders(...)` afterward, so nothing is ever left dirty in
memory relative to disk -- a crash or force-quit between two commands
never loses more than the single most recent change, matching the spec's
"save whenever the list changes" instruction literally.

### Firing: reused the existing tick, and the deliberate away exception

`_check_reminders()` is called from the existing `_on_system_tick` (the
same ~7s timer already driving the badge/idle/curiosity checks), per the
spec's explicit "no new timer" instruction -- there wasn't one single
timer that literally drives badge *and* streak *and* idle as the spec's
wording suggested (badge/idle/curiosity are on the 7s system tick; streak
is on a separate 5s tick), so this was hooked into the 7s one specifically
because that's also where `_check_idle` (and its away->active transition
hook) already lives, which this feature needs to share directly.

**The deliberate exception, implemented exactly as specced and worth
restating plainly**: v1.8 suppressed one-liners, curiosity, and the
mouse-chase spawn while `AWAY`, because those are ambient personality
touches nobody benefits from seeing with nobody there to see them. A
reminder is the opposite case -- the user explicitly asked for it at a
specific time, so `_check_reminders()` does **not** thread an `is_away`
suppression parameter into anything the way `should_show_oneliner`/
`should_spawn_mouse`/`should_react_to_new_launch` do. Instead:

- **Due while present** (`self._is_away is False`): `_check_reminders()`
  fires it immediately via `_fire_reminders()`, exactly like every other
  command reply -- removed from `self.reminders`, persisted, shown via
  `window.show_nudge(...)`.
- **Due while `AWAY`**: `_check_reminders()` returns immediately without
  touching anything -- the reminder stays in `self.reminders`, still due
  on every subsequent tick, never removed and never shown, until someone's
  actually there to see it.
- **The away->active transition**: `_check_idle()` (v1.8's existing hook,
  reused rather than adding a second "the user just came back" check, per
  the spec) now also calls a new `_flush_due_reminders()` at exactly the
  same point the welcome-back message already fires from. This recomputes
  `due_reminders(self.reminders, time.time())` fresh (not relying on
  whatever `_check_reminders()` last saw, since that could be stale by up
  to the ~7s tick interval) and fires all of them through the same
  `_fire_reminders()` helper both paths share -- one reply if exactly one
  came due, a combined "N reminders came due: ..." reply
  (`format_flushed_reminders_reply`) if several piled up during one
  absence, since the nudge bubble can only hold one message at a time and
  there's no queue.

**A precedence call this session had to make, not specified by the spec
in this much detail**: what happens when the away->active transition
*also* would have shown v1.8's generic welcome-back message (a long-enough
absence)? Decided that a flushed reminder -- concrete, user-requested
content -- wins over the ambient "خوش برگشتی" line, rather than trying to
show both back-to-back or letting them race for the one nudge slot:
`_check_idle` only shows the generic welcome-back message when
`_flush_due_reminders()` returns `False` (nothing was pending to flush).
A short absence with a due reminder still flushes it even though it's
below the 30-minute welcome-back threshold -- that threshold was always
specifically about not nagging with an *ambient* greeting on every short
break, which has nothing to do with a reminder the user actually set.

**`_fire_reminders(due)` is the one shared helper both paths call**,
avoiding a second copy of the "remove from the list, persist, pick single-
vs-combined reply" logic -- consistent with this codebase's standing
"reuse existing mechanisms rather than duplicate them" discipline applied
one level further than the spec's own letter (the spec only asked for the
present-vs-away distinction, not that the two firing *call sites* share
code, but doing so was the obviously simpler and more maintainable choice
once both needed nearly identical logic).

### Testing

`pytest -q` -> **202/202 passed** (167 pre-existing + 35 new
`test_reminders.py` + a `test_commands.py` update extending the existing
help-text-mentions-every-command test to cover `remind`/`reminders`/
`cancel` too, no new file needed there since it was already parametrized
over command names).

**Dispatch wiring, live against a real `GittenApp`, not a mock** (per the
spec's explicit "the same way v1.9's Part 2 was verified" instruction): a
scratch script drove `_dispatch_command` directly through a full, real
lifecycle -- both malformed `remind` cases (no duration, duration with no
message, non-numeric duration) correctly returned the usage hint and
created nothing; a real `remind 10m take a break` returned the exact
expected confirmation text, appeared in `self.reminders`, and was
genuinely persisted to the real `~/.gitten/reminders.json` on disk (read
back and printed to confirm, not just asserted in memory); a second
reminder got id `2`; `reminders` listed both, correctly sorted by
soonest-due rather than insertion order; `cancel` with no id and with an
unknown id (`999`) both returned their usage/unknown-id replies without
touching the pending list; a real `cancel 1` removed exactly that one and
returned its confirmation; cancelling the same id again afterward cleanly
reported it unknown (proving the removal was real, not a no-op); and
`help` now lists all three new commands. The test-created
`~/.gitten/reminders.json` (this machine had no pre-existing one) was
removed afterward so this session doesn't leave a stray file behind for
the real app -- confirmed via `ls` before writing anything to it and `rm
-rf ~/.gitten` after.

**The away-hold-and-flush timing -- the one genuinely new piece of timing
logic this round adds -- verified live and specifically, per the spec's
explicit instruction not to leave this one only unit-tested**: using the
same "monkeypatch `gitten.main.get_idle_seconds` -- a plain Python
function reference, not a compiled Qt/Shiboken method" technique v1.8's
own live test already established as safe in this codebase (see section
19), against a real, fully-wired `GittenApp`:

1. Forced a real away transition (`get_idle_seconds` returning 700s, over
   the 600s threshold) via a real `_check_idle()` call -- confirmed
   `self._is_away`/`window._away` both flipped to `True`.
2. Set a real reminder due in 2 real seconds (`remind 2s some task`) while
   already away, waited for real wall-clock time to actually pass it, then
   called the real `_check_reminders()` -- confirmed `window._nudge_text`
   stayed `None` and the reminder was still sitting in `self.reminders`,
   proving it did **not** fire into the nudge bubble while away. Called
   `_check_reminders()` a second time to confirm repeated away-ticks don't
   do anything different either (no partial state, no accidental firing on
   a later poll).
3. Flipped `get_idle_seconds` back to `0.0` and called the real
   `_check_idle()` again -- confirmed the away->active transition fired
   exactly then: `window._nudge_text` became `"⏰ some task"`,
   `self.reminders` emptied, and `self._is_away`/`window._away` both
   correctly flipped back to `False`.
4. Two further live checks, each in its own fresh process (a `QApplication`
   is a process-wide singleton -- confirmed the hard way, a first attempt
   at running both in one script crashed with `RuntimeError: libshiboken:
   Please destroy the QApplication singleton before creating a new
   QApplication instance` on the second `GittenApp()`): a reminder due
   while genuinely present fires immediately on the very next
   `_check_reminders()` tick, no waiting for any transition; and two
   reminders piling up during one simulated absence flush together as a
   **single combined** reply (`"while you were away, 2 reminders came
   due: first; second"`) at the transition, not one bubble each,
   confirming `_fire_reminders`'s single-vs-combined branching is what
   actually runs, not just reasoned about.
5. A regression check confirmed v1.8's own welcome-back message is
   completely unaffected when there's nothing to flush: a long simulated
   absence (`_away_since` backdated well past the 30-minute threshold)
   with zero pending reminders still produced the original
   `"خوش برگشتی 🙂"` message exactly as before this session's changes to
   `_check_idle`.

All scratch scripts' `~/.gitten` test artifacts were removed afterward and
`tasklist` was checked clean after every run, avoiding a repeat of the
zombie-process lesson recorded earlier this same round (section 20's
bugfix entry) and originally in section 4.

With this, all four parts of v1.10 (pure logic, persistence, the three new
commands, and the away-hold-and-flush firing behavior) are implemented,
tested, and documented, and the settings panel / dashboard rounds the spec
mentions can now build on real, persisted reminder data.

## 22. Reminder-alert bugfix + design: the nudge bubble was clipped, and reminders now look like alerts

A bug report plus a design request, both about the nudge bubble
(`sprite._draw_speech_bubble`), the mechanism v1.10's reminders reuses for
their reply text. Investigated and fixed with the same standard the v1.9
command-bar backdrop bug held itself to: real `QScreen.grabWindow`
screenshots, actually opened and looked at, not just internal-state
assertions.

### Bug: the bubble was a "blank/white flash"

**Reproduced first, before touching any code**: a real, visible
`KittenWindow`, a real `show_nudge()` call, and a real screen grab of the
region above the cat (where the bubble draws) confirmed the report --
mostly blank, no legible text.

**Root cause, found by computing the bubble's actual geometry, not by
guessing**: the bubble's vertical anchor was `center.y() - BODY_RY * 1.9 -
bubble.height() / 2`, which pins the bubble's *bottom* edge at a fixed
canvas y (~13) regardless of its height. At this font size the bubble is
~26 canvas units tall, so its *top* edge landed at roughly y=-13 -- well
above the canvas's own y=0 top edge. Qt clips all painting to the widget's
own bounds, and this window is only ~130px tall with nothing above it, so
the top half of the bubble -- including the text, vertically centered
within that top half -- was silently clipped off screen on **every**
nudge this app has ever shown, not just reminders. This was never caught
before because every prior session verified nudges by checking
`window._nudge_text` (an internal string), never by actually
screenshotting a live, positioned window -- confirmed numerically first
(`bubble.top() ≈ -13`) and then visually, exactly the same "internal state
looked right, but nobody had actually looked at the pixels" root cause as
the v1.9 command-bar backdrop bug two sessions ago.

**Fix, Part 1 -- vertical**: a new fixed `_NUDGE_BUBBLE_BOTTOM_OFFSET =
BODY_RY * 1.05` (clearing the resting ear tips with margin to spare,
tuned and re-verified against a real screenshot rather than trusted from
the math alone) replaces the old `BODY_RY * 1.9`, plus a defensive `if
bubble.top() < 2: bubble.moveTop(2)` clamp added alongside the *existing*
left/right clamps in the same function -- the bug was really that the
function clamped two sides and silently forgot the third, an incomplete
implementation of its own existing pattern, not a new concept.

**Fix, Part 2 -- horizontal, found through the same rigor, not assumed
fixed**: verifying the vertical fix with a screenshot of a long reminder
message (`"while you were away, 2 reminders came due: first; second"`)
surfaced a *second*, more fundamental clipping bug: that text is simply
wider (~320 canvas units at 9pt bold) than the entire 128-unit canvas /
~130px window, so no amount of repositioning within the existing window
could ever fit it on one line, and wrapping it would need more vertical
room than the fix above provides either. **This affects any long reply
this codebase can produce**, not just reminders -- v1.9's own
`COMMANDS_HELP_TEXT` is comparably long. Real fix: the window itself now
temporarily *widens* to fit a wide bubble, mirroring the exact resize
pattern the v1.2 notification inbox already established
(`_resize_anchored_bottom_right`), just anchored at the bottom-*center*
instead of bottom-right (the cat is always drawn horizontally centered in
this window, so growing width-only while keeping the center and bottom
edge fixed is what lets the window widen without the cat's own on-screen
position ever visibly shifting):

- `sprite.nudge_bubble_size(text, alert)` is a new small pure function --
  the single source of truth for the bubble's natural (unclamped)
  single-line size in canvas units, extracted out of
  `_draw_speech_bubble`'s own geometry math so it can be called from
  `window.py` too without the two ever drifting out of sync with each
  other.
- `KittenWindow._grow_for_nudge(text, alert)`, called from `show_nudge()`,
  computes the physical pixel width needed (capped at 4x the base window
  size, so pathological input can't produce an absurdly wide window) and
  resizes via a new `_resize_anchored_bottom_center` -- built with
  `QRect.moveCenter` + `QRect.moveBottom` (Qt's own accessors), the same
  "don't hand-roll the arithmetic" lesson the v1.2 dev notes already
  recorded after an inclusive-`bottomRight()` off-by-one bug there.
- `_shrink_to_base_size()` resizes back down once the nudge actually
  expires. Moving *when* that happens required a small refactor:
  mutating widget geometry from inside `paintEvent` (where the old
  `_nudge_opacity` used to clear expired nudge state) is risky in Qt, so
  expiry detection moved to a new `_check_nudge_expiry()`, called from the
  existing `_on_animation_tick` (outside any paint call) instead;
  `_nudge_opacity` is now a plain, side-effect-free read.
- `paint_kitten` computes `canvas_half_width = rect.width() / (2 *
  scale)` (normally exactly `CANVAS/2`, wider once the window has grown)
  and threads it into `_draw_speech_bubble`'s left/right clamps, so a wide
  bubble can actually use the extra room instead of still being clamped to
  the original narrow bound.

**Testing -- live, with real screenshots actually opened and inspected,
per the explicit instruction**: the same real-window/real-`show_nudge`
script used to reproduce the bug was re-run after each fix. A regular
short nudge (`"Commits today: 3"`) now renders fully inside a correctly
positioned bubble, no clipping. The long combined-reminder message now
renders **on one line, in full**, inside a visibly widened window (628px
window at that geometry vs. the base 130px), confirmed both by opening
the saved PNG and by the window's own reported geometry growing as
expected. `pytest -q` -> unchanged at **202/202 passed** (this was Qt
rendering/geometry code with no new pure-logic module).

### Design: reminders now look like an alert, not a routine nudge

Per the request, reminder-sourced nudges get a visibly distinct
treatment, implemented as an additive `alert: bool` parameter threaded
through `show_nudge` -> `paint_kitten` -> `_draw_speech_bubble` (default
`False`, so every existing call site -- one-liners, the distraction
nudge, the welcome-back message -- is completely unaffected, the same
additive-parameter discipline every feature in this codebase has used
since v1.1's badges):

- **A distinct color treatment**: a warm amber fill (`#FFF3E0`) and a
  bold `#FB8C00` border (2.2px vs. the regular bubble's 1.6px) -- reusing
  this codebase's *existing* low-battery-badge amber
  (`status_badge.Badge.LOW_BATTERY`'s color in `sprite.py`) rather than
  inventing a new "urgent" color from scratch, since it already reads as
  "pay attention" here.
- **Bold text** (`QFont.Bold`) instead of the regular nudge's normal
  weight.
- **A small drawn alarm-clock icon** (`_draw_alarm_icon`, new) at the
  bubble's left edge -- a circle with two small "feet" (reading as an
  alarm clock specifically, not a plain clock face) and two hands in the
  accent color, plus a small continuous side-to-side "ring" jitter reusing
  the same sine-wiggle idiom as the purr reaction's ear wiggle. Matches
  the clock imagery already established by `reminders.format_due_reply`'s
  original emoji -- which is why that emoji was then **removed** from the
  reply text itself (`reminders.py`): once the bubble draws its own alarm
  icon, keeping a matching "⏰" glyph in the text was redundant, confirmed
  visually (a live screenshot showed both at once, looking like an
  unintentional double icon) before removing it, not just assumed.
- **A noticeably longer display duration**: `show_nudge` gained a
  `duration` parameter (defaulting to the existing `NUDGE_DURATION_SECONDS`
  = 4s for every other caller); reminders pass the new
  `REMINDER_NUDGE_DURATION_SECONDS = 9s`, more than double, "long enough
  to comfortably read" even the combined multi-reminder flush message.
- **A small pop-in entrance**: over the reminder's first 0.22s on screen,
  the bubble scales in from 0.6x to 1.0x (`_ALERT_POP_SECONDS`) --
  computed from a new `nudge_elapsed` value `window.py` threads through
  (captured *before* `_nudge_opacity` runs, since that call can clear the
  nudge's start time the instant it expires). Regular nudges pass
  `elapsed=0.0`/`alert=False` and keep their plain opacity-only fade-in
  completely unchanged -- this animation is reminder-specific emphasis,
  not a new universal behavior.

`main.py`'s `_fire_reminders` (the one place reminders actually reach the
nudge bubble, for both the present-tick and away-flush firing paths --
see section 21) is the only call site that passes
`duration=REMINDER_NUDGE_DURATION_SECONDS, alert=True`; every other
`show_nudge` call in the codebase is untouched and keeps the plain look.

**Testing -- live screenshots, plus the same pixel-diff standard this
codebase already holds itself to for "genuinely distinct, not just
reasoned about" claims (v1.5's purr-vs-focused, v1.6's curious-vs-focused,
v1.8's away-vs-idle)**:

- A live screenshot of a real fired alert bubble (`"take a break"`)
  actually opened and inspected: amber border, warm fill, bold text, and
  the alarm icon with its two feet, clearly legible and clearly not the
  same look as the plain white regular-nudge bubble shown alongside it in
  an earlier screenshot in this same session.
- A same-text, alert-vs-regular off-screen render pixel-diff: **6,766
  differing pixels** out of a 200x200 canvas -- confirms the alert styling
  is a substantial, genuine visual difference, not a subtle tweak that
  happens to pass eyeballing.
- The pop-in animation's own effect on the rendered image, verified
  numerically rather than assumed from reading the code: rendering the
  same alert bubble at `elapsed=0.0`, `elapsed=0.1`, and `elapsed=0.3`
  (past the 0.22s pop window, fully settled) showed 5,898 differing
  pixels between the start and settled frames and 4,656 between the
  mid-pop and settled frames -- confirms the scale-in genuinely animates
  rather than being dead code that never actually executes differently
  frame to frame.
- **The full real path, end to end**: a real `remind 1s finish the pr
  review` set through `_dispatch_command`, left to actually become due,
  fired through the real `_check_reminders()` tick (not a manual
  `show_nudge` call) -- confirmed `window._nudge_alert` was `True`, the
  text was correct, and a real screenshot of the result shows exactly the
  alert-styled bubble described above, produced by the real reminder
  machinery rather than a hand-constructed test scenario.
- `pytest -q` -> unchanged at **202/202 passed** (`format_due_reply`'s
  emoji removal didn't change any existing assertion, since no test
  checked for the literal emoji character -- only substring/content
  checks, confirmed by grepping for it in the test file before removing
  it from the source).

All scratch test scripts' screenshots and any `~/.gitten` test artifacts
were kept out of the repo (scratchpad-only) and `tasklist` was checked
clean after every live run.

## 23. Working agreement for this project

**Every change made to this codebase must be recorded in this file
(`DEVELOPMENT_NOTES.md`) in the same session it's made** — what was
built, why, and how it was tested — not just left implicit in the diff or
in a chat summary. This file is the durable record; treat updating it as
part of finishing the task, not an optional follow-up.

## 24. v1.11 -- the settings panel, and fixing several "load once at startup" bugs

Input is `GITTEN_V1_11_SPEC.md`. This round consolidates the configuration
that already existed -- scattered across three `~/.gitten/*.json` files and
a couple of tray dialogs -- into one real window, per the spec's explicit
scoping: **no new configurability was invented** (badge thresholds,
sulking/away timing, the hotkey combo, and spawn intervals all stay exactly
as hardcoded as they were before this session), and every tab's Save reuses
an existing apply/persist mechanism rather than writing a parallel one.

### Architecturally the first normal window in this app

Every prior window (`KittenWindow`, `MouseWindow`, `CommandBarWindow`) uses
`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool` +
`Qt.WA_TranslucentBackground`, because each is an overlay-style pet/game/
popup widget. The new `src/gitten/settings_window.py` deliberately does none
of that: `SettingsWindow(QDialog)` sets only `Qt.Window` and never touches
`WA_TranslucentBackground` or `WindowStaysOnTopHint` -- a normal title bar,
normal minimize/close, not always-on-top, not click-through, exactly per the
spec's explicit "don't copy the wrong precedent" instruction. Verified this
concretely rather than just trusting the code: a live script asserted
`windowFlags() & Qt.WindowStaysOnTopHint` and `& Qt.FramelessWindowHint` are
both false and `testAttribute(Qt.WA_TranslucentBackground)` is false on the
real, shown window (see Testing).

Five tabs (`QTabWidget`): General, Distraction, Focus, Telegram, Reminders.
Each of the first four has its **own** Save button (not one dialog-wide
Save) since each edits an independent config surface with its own
persistence file -- committing one tab's list edits shouldn't require also
committing whatever's mid-edit in another tab. The Reminders tab has no Save
button at all: it's a live view with an immediate per-row Cancel action, not
something staged and committed. A shared `_build_list_editor(initial_items)`
helper (a `QListWidget` + Add.../Remove buttons, `QInputDialog.getText` for
Add) is reused for every string-list surface -- distraction titles,
distraction processes, the focus substring list, and both Telegram lists --
rather than four near-identical copies.

The panel is created lazily on first open (`GittenApp._open_settings_panel`,
wired to both the tray's new "Settings..." action and the command bar's new
`settings` command) and reused on subsequent opens rather than spawning a
new window each time; `showEvent` refreshes every field to the app's actual
current live state (repo path, cat name, birthday, and the Reminders tab if
it's the active one) so reopening never shows stale data from a previous
open or from a change made through some other path (e.g. a `rename` command
typed into the command bar while the panel was closed).

### General tab -- three fields, three different reuse shapes

- **Repo path**: a read-only label + "Browse..." button that calls
  `self._app._prompt_choose_repo(required=False)` directly -- the *exact*
  existing method the tray's "Choose watched repo..." action already calls,
  which already does the file dialog, the `is_git_repo` validation (see
  below), the persist, and the tooltip refresh all together, live,
  immediately. This field has no separate Save step at all, since the
  existing method it reuses is already a single atomic live action.
- **Cat's name** / **birthday**: `QLineEdit`s, applied on this tab's Save
  button via `self._app._apply_rename(name)` (unchanged, already extracted
  in v1.9) and a **new** `GittenApp._apply_birthday(text) -> bool`, pulled
  out of `_prompt_set_birthday` the same way `_apply_rename` was pulled out
  of `_prompt_rename` back in v1.9 -- `_prompt_set_birthday` itself is now
  just "get text via QInputDialog, then call `_apply_birthday`". Both the
  tray dialog and the settings panel now share the one validate+persist
  path; an invalid date shows the same `QMessageBox.warning` either way.

**`git_watcher.py` gained `is_git_repo(path) -> bool`**, pulled out of
`GitWatcher.set_repo`'s inline `(repo_path / ".git").is_dir()` check into its
own small function -- exactly the "keep it in a small testable function"
instruction the spec calls out for repo-path validation, and it means
`set_repo` and any future caller (this session had none besides the existing
one, since the settings panel reuses `_prompt_choose_repo` rather than
re-validating itself) share one definition of "looks like a git repo." New
`tests/test_git_watcher.py` (this codebase's first test file for
`git_watcher.py`, which had none before since the rest of the module is I/O
this project has always verified live) covers a real `.git` directory, a
missing one, a `.git` *file* (submodule/worktree style -- deliberately not
treated as a match, matching the pre-existing behavior), a nonexistent path,
and a string-typed path argument.

### The part that mattered most: fixing "load once at startup, never again"

Three config surfaces were checked, per the spec's explicit instruction, for
whether they were only ever loaded once into in-memory state at `GittenApp.
__init__` and never re-read -- confirmed true for all three before writing
any fix:

- **Distraction lists**: `self.distracting_titles` / `self.distracting_processes`
  were loaded once via `load_distraction_lists` and never touched again;
  `_on_distraction_tick` reads them fresh every ~3s poll (`self.
  distracting_titles`, not a local copy), which turns out to make the fix
  trivial once the settings panel reassigns them directly -- no reload
  method needed, matching the spec's "or just reassign the attribute
  directly from main.py" option.
- **Distraction threshold**: a genuinely new gap, not just a stale-cache one
  -- `DistractionTracker` was always constructed with its hardcoded
  `DEFAULT_THRESHOLD_SECONDS` default; `load_distraction_lists` never even
  read a threshold key from `distraction_config.json` in the first place, so
  this wasn't configurable via hand-editing the JSON file either, despite
  the spec describing it as already living there. Added
  `load_distraction_threshold_seconds` (reads a new `threshold_minutes` key,
  same file, same fallback-to-default discipline) and
  `save_distraction_config(titles, processes, threshold_minutes, path)`
  (writes all three keys together) to `distraction.py`. `GittenApp.__init__`
  now constructs `self.distraction_tracker` *after* loading this value
  (previously it was constructed with no arguments before the lists were
  even loaded) rather than leaving it permanently stuck on the hardcoded
  default.
- **Focus substrings**: same shape as distraction titles/processes --
  `self.focus_substrings` is already read fresh every ~5s poll by
  `_on_focus_tick`, so reassigning it live is enough. Added
  `save_focus_substrings(substrings, path)` to `focus.py`.

**`GittenApp` gained three new `_apply_*` methods** (`_apply_distraction_config`,
`_apply_focus_config`, `_apply_telegram_lists`), each called from the
matching tab's Save button and each responsible for *both* halves of "Save"
per the spec's explicit instruction -- persist to disk **and** push into the
live in-memory state the running app actually reads -- rather than the
settings panel doing either half itself: `_apply_distraction_config` reassigns
`self.distracting_titles`/`self.distracting_processes` and replaces
`self.distraction_tracker` with a freshly-constructed one at the new
threshold (simplest correct way to change a running tracker's threshold
without hand-patching its internal `_next_fire_elapsed` watermark -- accepted
tradeoff: this does reset any distraction streak already in progress, judged
reasonable for a settings change); `_apply_focus_config` reassigns
`self.focus_substrings`; `_apply_telegram_lists` only persists (see below).

**Live-apply was verified live, not just reasoned about**, per the spec's
explicit instruction: a real `GittenApp` had its distraction titles/processes
list-widgets edited and Saved through the real `SettingsWindow`, then
`is_distracting_window` was called directly against the app's *own*
post-save `self.distracting_titles`/`self.distracting_processes` attributes
-- confirmed the new process (`game.exe`) now matches and the old one
(`discord.exe`) no longer does, with no restart anywhere in between. Same
live check for focus: after Saving a custom `["make check"]` substring list,
a real `python.exe` subprocess was launched and `is_focus_process_running
(app.focus_substrings)` correctly returned `False` against it (it doesn't
match "make check"), proving the *new* list is what's actually being
checked, not a stale default. See Testing below for the full script.

### Telegram tab -- a real gap between the spec's assumption and the codebase

The spec describes the Telegram tab as editing "the favorites/bad-sender
lists (`~/.gitten/telegram_lists.json`)" as if a load path for that file
already existed. It didn't: v1.3 (section 10) only ever built the standalone
connection-test script and `telegram_config.py` (the api_id/api_hash cache)
-- `telegram_watcher.py` and the actual favorite/bad-sender matching logic
described in `GITTEN_V1_3_SPEC.md` were never built, confirmed again by
`grep`ing this codebase for `telegram_lists`/`favorites` before writing
anything (matches section 15's "Roadmap rewritten accurately" finding from
two housekeeping rounds ago, still true). This isn't new configurability
being invented, though -- the JSON shape itself was already fully specified
by `GITTEN_V1_3_SPEC.md`, just never given a load/save path -- so building
that path is squarely what this tab is supposed to do, not scope creep.

**New `src/gitten/telegram_lists.py`**, same shape as `telegram_config.py`
and `distraction.py`'s list loader: `load_telegram_lists(path) -> (favorites,
bad)` (falls back to `([], [])`, since there's no shipped default sender
list the way there is for distraction/focus) and `save_telegram_lists
(favorites, bad, path)`. `GittenApp._apply_telegram_lists` only persists --
there's deliberately no live in-memory state to push this into, since
nothing in the running app reads `telegram_lists.json` back out yet. Once
`telegram_watcher.py` is eventually built, it should read via
`load_telegram_lists` here rather than re-deriving the file location, per
the same "one source of truth for where a config file lives" reasoning
`telegram_config.py`'s own docstring already gives for the credential/
session paths. The tab shows a short note explaining the connection itself
is still pending, per the spec's explicit instruction.

### Reminders tab -- view + cancel, reusing the exact existing path

Lists pending reminders (sorted soonest-due, same order `format_reminders_list`
already uses for the command-bar `reminders` reply) with a per-row Cancel
button. Clicking Cancel calls `self._app._handle_cancel_command(str(reminder_id))`
directly -- the exact same method the `cancel <id>` command-bar command
already calls, not a reimplementation -- then re-renders the row list.
Refreshed when the tab becomes visible (`QTabWidget.currentChanged`) and
whenever the whole dialog is reopened via `showEvent`, per the spec's
explicit allowance that a live-updating timer isn't needed here.

### Command bar + tray wiring

`commands.py` gained a `SETTINGS_OPENED_REPLY = "opening settings..."`
constant and `settings` was added to `COMMANDS_HELP_TEXT`, alongside the
existing eight. `GittenApp._dispatch_command` gained a `settings` branch
(calls `_open_settings_panel()`, returns the constant) following the exact
same shape every other handler already uses. The tray menu gained a
"Settings..." action (`_build_tray`), placed in its own section between the
rename/birthday actions and Quit.

### Testing

`pytest -q` -> **220/220 passed** (202 pre-existing + 18 new: 5
`test_distraction.py` additions for `load_distraction_threshold_seconds`/
`save_distraction_config`, 2 `test_focus.py` additions for
`save_focus_substrings`, 5 new `tests/test_telegram_lists.py`, 5 new
`tests/test_git_watcher.py`, and 1 `test_commands.py` addition for
`SETTINGS_OPENED_REPLY` plus extending the existing help-text-mentions-
every-command test to include `settings`). No new pure-logic module needed
a dedicated test file for the Qt-glue parts (`settings_window.py` itself),
matching this codebase's established pattern (no `test_main.py`,
`test_command_bar_window.py`, etc. have ever existed either) -- verified
live instead, per the spec's own explicit acknowledgment that "this round is
UI-heavy... don't force artificial pure-logic modules."

**Live, against a real (offscreen) `GittenApp` and a real scratch git
repo** -- a scratch script drove the actual `SettingsWindow` instance
end-to-end, nothing mocked: opened the panel (confirmed lazy-creation +
reuse-on-reopen), edited and saved General (name/birthday applied via the
shared methods, confirmed on `app.cat_name`/`app.birthday`; repo path
applied live via a monkeypatched `QFileDialog.getExistingDirectory` pointed
at a real `git init`-ed scratch repo, confirmed on `app.watcher.repo_path`),
edited and saved Distraction (confirmed both the live in-memory attributes
*and* the on-disk JSON, plus a real `is_distracting_window` call against the
new lists), edited and saved Focus (confirmed live `app.focus_substrings`
against a real running subprocess, plus on-disk JSON), edited and saved
Telegram (confirmed on-disk JSON, no live consumer to check since none
exists yet), set two real reminders via `_dispatch_command("remind", ...)`
and cancelled one through the Reminders tab's Cancel button (confirmed
`app.reminders` actually shrank by exactly the cancelled one), confirmed
reopening the reused panel shows the just-applied name/repo rather than
stale values, and confirmed the command bar's `settings` command opens the
same panel instance. All ten checks passed.

**Real screenshots, actually opened and inspected, not just internal-state
assertions** -- per this codebase's established standard for any new Qt UI
(the v1.9 command-bar backdrop bug and the v1.10/section-22 nudge-bubble
clipping bug were both real rendering bugs that internal-state assertions
alone had missed in earlier sessions). A live, non-offscreen `GittenApp` had
its settings panel opened, `QScreen.grabWindow` captured the General,
Distraction, and Reminders tabs (switching tabs via `QTest.qWait(300)`
first, not just calling `setCurrentIndex` -- an earlier version of this
script grabbed identical screenshots for every tab because Qt hadn't
actually repainted yet without a processed event loop turn). All three PNGs
were opened and visually inspected: General shows the watched-repo path,
Browse button, name/birthday fields, and Save, with real window chrome (a
title bar) unlike every other window in this app; Distraction shows both
list widgets populated with the real defaults, Add/Remove buttons, the
threshold spinbox at its correct default (20), and Save; Reminders shows two
real pending reminders sorted by time-left with working per-row Cancel
buttons. This also visually confirmed `windowFlags()`/`WA_TranslucentBackground`
match what the live script already asserted programmatically -- an actual
opaque white panel with a native title bar, not a transparent overlay.

**A test-hygiene note worth recording**: this session's live scripts wrote
real values into the actual `HKCU\Software\Gitten\Gitten` `QSettings` key
(cat name, birthday, repo path) -- unlike `~/.gitten/*.json`, prior sessions'
dev notes never mention scrubbing `QSettings` after a live test, but leaving
a scratch-test repo path pointing at a since-deleted temp directory would
have left the *real* app's next launch pointing at nothing. Reset
`cat/name`, `cat/birthday`, and `repo/path` back to unset (first-run state)
after both live scripts finished, via a small standalone `QSettings` cleanup
call. All `~/.gitten/*.json` test artifacts were removed afterward and
`tasklist` was checked clean after every live run, per this project's
standing process-hygiene discipline.

## 25. v1.12 -- the dashboard, and a `git log --since` footgun found while building it

Input is `GITTEN_V1_12_SPEC.md`. A single read-only "at-a-glance" status
window -- unlike the settings panel, nothing here is editable -- reusing the
exact same normal-window precedent `settings_window.py` established one
round ago, and reusing existing data sources end to end rather than adding
new monitoring/query logic anywhere.

### `src/gitten/dashboard_window.py` -- the second normal window

`DashboardWindow(QDialog)` sets only `Qt.Window`, same as `SettingsWindow` --
no transparency, no always-on-top, a real title bar. Verified the same way
`settings_window.py` was: a live script asserted `windowFlags() &
Qt.WindowStaysOnTopHint`/`& Qt.FramelessWindowHint` are both false and
`testAttribute(Qt.WA_TranslucentBackground)` is false on the real, shown
window. Reached the same two ways every other window in this app is: the
tray's new "Dashboard..." action (`_build_tray`, right next to "Settings...")
and the command bar's new `dashboard` command (`commands.
DASHBOARD_OPENED_REPLY`, added to `COMMANDS_HELP_TEXT`). Same lazy-create-
and-reuse pattern as `_open_settings_panel`: `GittenApp._open_dashboard`
creates a single `DashboardWindow` on first call and reuses it afterward.

Six sections, top to bottom:

- **Cat identity**: name (bold), current state in plain words, and session
  uptime -- reuses `self._app._format_uptime()` directly (unchanged,
  already existed) rather than recomputing it. State is `away` when
  `self._app._is_away`, else `sulking` when `attention_tracker.state ==
  AttentionState.SULKING`, else the git-driven `Mood` in plain words (a
  small `_MOOD_LABELS` dict maps `Mood.WAITING` to "waiting for a commit"
  rather than the bare enum value "waiting", for readability) -- away and
  sulking take priority since they're the more specific, more recently-true
  state, matching the same precedence `sprite.py` already gives sulking
  over the focused-reaction face (v1.4 dev notes, Feature 2).
- **Streak calendar heatmap**: a hand-drawn `QPainter` grid
  (`_HeatmapWidget`, 12 columns/weeks x 7 rows/weekdays), no external
  charting library -- the same "draw it yourself with primitives" approach
  every other visual surface in this app uses. Shaded by `streak.
  commits_by_day(dates, weeks=12)` against four fixed count thresholds (1,
  2-3, 4-6, 7+), deliberately fixed rather than relative to the window's own
  max so the same count always reads the same shade.
- **Current + best streak, side by side**: `get_commit_streak` (existing,
  unchanged) for current, and a new `streak.longest_streak(dates)` for best-
  ever -- a genuinely different calculation from the current-streak one, not
  a rename of it (see below).
- **This week's commits**: a new `git_watcher.count_commits_this_week`,
  widened from `count_commits_today`'s existing `--since=midnight` shape to
  the start of the current week -- see the footgun below for why this
  needed a real fix mid-session, not just a mechanical widening.
- **System snapshot**: `system_monitor.sample_system()`, called directly,
  display-only -- no new monitoring logic, exactly per the spec.
- **Pending reminders**: reuses `reminders.sorted_by_due`/
  `format_reminder_row` (see below) -- read-only here (no Cancel buttons,
  per the dashboard's "not editable configuration" scope), just the sorted
  list of `format_reminder_row` lines.

Refresh: `DashboardWindow.refresh()` recomputes and redraws every section.
Called from `__init__` (first paint), `showEvent` (every reopen), and --
per the spec's explicit "piggyback on the existing ~7s system tick, no new
timer" instruction -- from `GittenApp._on_system_tick`, guarded by `if
self._dashboard_window is not None and self._dashboard_window.isVisible()`
so a closed/hidden dashboard costs nothing on every tick.

### `streak.py` -- two new pure functions, built from the same git data

- **`commits_by_day(commit_dates, weeks=12, today=None) -> dict[date, int]`**:
  every day in the `weeks`-week window ending `today` is present in the
  result (0 if no commits that day), not just days with activity, so the
  heatmap widget never has to special-case a missing key. `today` is
  injectable, same "pass in the clock" idiom `compute_streak` already uses,
  for fake-date testability.
- **`longest_streak(commit_dates) -> int`**: the longest run of consecutive
  days *anywhere* in the full history, genuinely different from
  `compute_streak` (which only ever measures the current run ending today
  or yesterday) -- O(n): for every day whose previous day has no commit
  (i.e. every possible streak start), count forward from there, so no day
  is ever re-walked as part of more than one candidate run.

Both consume the exact same `YYYY-MM-DD` date-string shape `compute_streak`
already does, fed from a **new `git_watcher.get_commit_dates(repo_path)`**
-- the raw, non-deduplicated list of one date per commit, pulled out of what
used to be `get_commit_streak`'s own inline `git log --format=%ad
--date=short` call + set-comprehension dedup. `get_commit_streak` itself now
just calls `get_commit_dates` and passes the result straight to
`compute_streak` (which already builds its own set internally, so passing
duplicates through is harmless) -- this is the "don't add a second,
differently-shaped git query" instruction satisfied structurally: there is
now exactly one function in the codebase that runs this git command, and
`get_commit_streak`/`commits_by_day`/`longest_streak` all consume its output
rather than three independent subprocess calls.

### `reminders.py` -- two small pieces shared between the settings panel and the dashboard

Per the spec's explicit instruction to reuse "the exact same list-building
logic the settings panel's Reminders tab already has," pulled the two
pieces that logic was actually made of out into `reminders.py` itself
(previously inlined directly in `settings_window.py`):

- **`sorted_by_due(reminders) -> list[Reminder]`** -- `sorted(reminders,
  key=lambda r: r.due_at)`, trivial but now genuinely one definition instead
  of independent copies.
- **`format_reminder_row(reminder, now) -> str`** -- the
  `#id "message" (Xm Ys left)` line, pulled out of what used to be an
  f-string inline in both `format_reminders_list` and
  `settings_window._refresh_reminders_tab`.

`format_reminders_list` (the command-bar `reminders` reply) was refactored
to use both, so there are now three call sites (`reminders` command,
settings panel, dashboard) sharing one sort and one row-format instead of
three copies that could silently drift apart. `settings_window.
_refresh_reminders_tab` was updated to use them too rather than left as the
one remaining inline copy.

### A real `git log --since` footgun, found live while building this

`count_commits_this_week` started out as the mechanical "widen `count_commits_today`'s
`--since=midnight` to the start of the week" the spec describes: `--since=
{week_start.isoformat()}` (a bare `YYYY-MM-DD`). Live-testing it against a
real scratch repo with a real commit made *today* returned **0** -- wrong.
Chased down by hand, not assumed:

- `git log --since="2026-08-31 00:00:00" --oneline` (explicit midnight)
  correctly found the commit.
- `git log --since=2026-08-31 --oneline` (bare date, no time, and that date
  is *today*) returned **nothing**, reproducibly, on the same repo.
- `git log --since=2026-08-30 --oneline` (bare date, but *not* today) found
  it correctly.

Git's `approxidate` parser does not reliably default a bare, no-time date
string to that day's midnight when the date in question is today -- this is
exactly the trap `count_commits_today` already avoids, by a different route:
it uses the literal word `"midnight"` (which `approxidate` always treats as
"00:00:00 today" unambiguously), never a computed date string. Fixed by
giving `count_commits_this_week` an explicit time component too --
`--since=f"{week_start.isoformat()} 00:00:00"` -- which sidesteps the
ambiguity the same way the manual `"2026-08-31 00:00:00"` test above did.
Documented directly in the function's own comment so a future session
reaching for `--since=<computed date>` anywhere else in this codebase
doesn't rediscover this by hand again.

**A second, separate footgun found while building this session's own
screenshot test data, worth recording since it could resurface in any
future live test that backdates commits**: a first version of the
screenshot script's scratch-repo builder created 70 backdated commits by
iterating a day-offset counter *upward* (today first, 69-days-ago last),
which makes today's commit the repo *root* and the 69-days-ago commit
*HEAD* -- backwards from how any real repo is ever built, where HEAD is
always the newest commit. `git log --since=...`'s early-termination
optimization assumes history is walked newest-to-oldest from HEAD, so
against this artificially-reversed history it stopped at the very first
commit it saw (HEAD, 69 days old, older than the cutoff) and concluded
there was nothing newer *anywhere*, silently undercounting despite several
genuinely-recent commits sitting deeper in the chain. Not a Gitten bug --
`count_commits_this_week`/`count_commits_today` are only ever exercised
against real repos, which are never built backwards like this -- but it
cost real debugging time before the cause was found, so the fix (iterate
oldest-day-first, so HEAD ends up being today's commit like a real repo)
is recorded here for any future session writing a similar backdated-commit
test script. Worth flagging as a known, inherent limitation of both
`--since`-based functions (`count_commits_today`, `count_commits_this_week`):
a real repo whose commit graph doesn't line up with commit-date order (an
unusual history from rebases, cherry-picks across branches, or a wrong
system clock at commit time) could in principle undercount the same way --
`get_commit_dates`/`commits_by_day`/`longest_streak` are immune to this
since they never use `--since` at all, just an unfiltered `git log` over
the full history.

### Testing

`pytest -q` -> **234/234 passed** (220 pre-existing + 14 new: 5
`test_streak.py` tests for `commits_by_day` (empty history, window
size/bounds, a history spanning fewer than the requested weeks, multiple
commits on the same day, dates outside the window ignored), 5 for
`longest_streak` (empty, no gaps, one gap picks the longer run, best run in
the past rather than the most recent run -- the exact case an
only-checks-the-current-run implementation would get wrong -- and
duplicates not inflating it), 3 `test_reminders.py` tests for
`sorted_by_due`/`format_reminder_row`, and 1 `test_commands.py` addition for
`DASHBOARD_OPENED_REPLY`. No dedicated test file for `dashboard_window.py`
itself, matching this codebase's established pattern for Qt-glue windows
(neither `settings_window.py` nor `command_bar_window.py` have one either)
-- verified live instead.

**Live, against a real (offscreen) `GittenApp` and a real scratch repo with
a genuine 5-day best-ever streak (well in the past) and a separate 1-day
current streak (today)** -- deliberately shaped so an implementation that
only ever looked at the current run would get "best" wrong, the same case
the unit tests cover in isolation, now proven through the real reused
`git_watcher`/`streak.py` functions end to end: opened the dashboard
(confirmed lazy-creation), asserted the current/best streak labels, the
this-week-commits label, and the heatmap widget's stored counts all exactly
match calling `get_commit_streak`/`longest_streak`/`count_commits_this_week`/
`commits_by_day` directly against the same repo (not just "some plausible
text"), confirmed the identity section shows the real cat name and mentions
uptime, confirmed the system section's labels are populated from
`sample_system()`, set two real reminders and confirmed the Reminders
section lists them soonest-due-first, confirmed the command bar's
`dashboard` command opens the same reused window instance. **The live
periodic-refresh requirement specifically** (the one the spec calls out as
needing more than a static check): made a brand-new real commit in the
watched repo while the dashboard was open, called the real
`_on_system_tick()` (not a manual `dashboard.refresh()`), and confirmed the
"Commits this week" label actually changed to reflect it -- with the window
never closed or reopened in between; then confirmed the inverse just as
carefully -- hiding the dashboard and making another new commit did **not**
change its (now-stale, correctly so) label until `_on_system_tick` ran
again, proving the `isVisible()` guard genuinely gates the refresh rather
than it running unconditionally; then reopening picked the change back up
via `showEvent`.

**Real screenshots, actually opened and inspected from the start** (per the
spec's explicit instruction to hold this new window to the same standard
`settings_window.py` was held to only after a bug report, not before) -- a
live, non-offscreen `GittenApp` with a real scratch repo (~70 backdated
commits scattered realistically across 12 weeks, plus a real 4-day current
streak and a real longer best streak, plus two real pending reminders) had
its dashboard opened and `QScreen.grabWindow` captured, actually opened and
looked at: the identity line, a correctly-shaded heatmap grid (light gray
for empty days, progressively darker green for busier ones), current/best
streak figures, a non-zero this-week count, all four system readings, and
both reminders listed soonest-due-first -- all present, legible, and
correctly laid out in a single scrollable-height column.

All scratch repos' temp directories and `~/.gitten/*.json` test artifacts
were removed afterward, and `HKCU\Software\Gitten\Gitten\repo` (pre-seeded
so `_restore_repo` wouldn't open a real blocking file-choose dialog in a
non-interactive script, same technique v1.11's screenshot script used) was
reset back to unset in each script's `finally` block. **One thing noticed
but deliberately left untouched**: two real `python -m gitten.main`
processes were found already running on this machine partway through this
session (confirmed via their real command line, not guessed) -- these are
the user's own actual app instances, not anything spawned by this session's
test scripts (which never invoke `-m gitten.main`), so they were left alone
rather than killed.

## 26. Housekeeping: README overhaul (post v1.6-v1.12) & version bump

Input is `GITTEN_HOUSEKEEPING_2_BRIEF.md`. Same standard as the first
README housekeeping round (section 15): `DEVELOPMENT_NOTES.md` was read in
full before writing a word of the new README, not reconstructed from
memory of the eleven spec files -- the README hadn't been touched since
that first pass (after v1.5), so everything from v1.6 (curiosity) through
v1.12 (the dashboard) was completely undocumented for anyone browsing the
repo: the mouse-chase minigame, real away detection + the welcome-back
message, the command bar and its now-twelve commands, reminders, the
settings panel, and the dashboard.

**Rewrote `README.md` end to end**, following the brief's own section
list:

- **Feature list regrouped by how you interact with it**, per the brief's
  own suggested framing, rather than staying purely categorical: "the
  ambient companion side" (mood, badges, distraction/focus reactions,
  curiosity, presence/away, personality/interaction, notifications,
  personalization -- everything that happens on its own) and "the
  assistant-tool side" (the command bar, settings panel, dashboard --
  everything you actively invoke). The old flat category list was folded
  into the first half rather than discarded, since the categories
  themselves were still accurate, just needed a level above them.
- **A new "Command bar" section** with the hotkey and a full command
  table, **pulled from `commands.py`'s actual `COMMANDS_HELP_TEXT` and
  `_dispatch_command`, not from memory of the specs** as the brief
  specifically warned -- confirmed this mattered: the original v1.9 spec
  only ever specified `streak`/`commits`/`battery`/`rename`/`chase`/`help`/
  `quit`; `remind`/`reminders`/`cancel` (v1.10) and `settings`/`dashboard`
  (v1.11/v1.12) were added in later rounds and would have been missed
  entirely working from spec memory alone.
- **A new "Windows" section** explaining the overlay-vs-normal window
  split plainly, pulling the exact flag combinations from the source
  (`window.py`/`mouse_window.py`/`command_bar_window.py` vs.
  `settings_window.py`/`dashboard_window.py`) rather than paraphrasing.
- **Configuration table updated** to lead with the settings panel as the
  primary way to configure things now, while explicitly keeping the
  underlying JSON file paths/shapes documented for anyone who prefers
  hand-editing (the panel reads/writes the exact same files, nothing about
  their location changed) -- plus a new explicit line for what the settings
  panel deliberately does **not** cover (badge thresholds, sulking/away
  timing, the hotkey combo, spawn intervals), since v1.11's own spec was
  explicit that scoping those out was deliberate, not an oversight, and a
  reader shouldn't be left assuming Settings is now fully comprehensive.
- **"How it's built" gained a second paragraph**, per the brief's "your
  call whether that's genuinely additive" instruction -- judged that it
  was: the existing independent-overlay-layers principle only explains the
  *ambient* half of the app now, and the assistant-tool half genuinely
  runs on a second, different principle worth naming (one shared
  implementation/several thin entry points -- `commands.py`'s dispatch
  table calling the same methods the tray already calls, and `reminders.py`'s
  `sorted_by_due`/`format_reminder_row` now shared by three separate UI
  surfaces). Not padding -- this is a real, distinct architectural pattern
  from the first paragraph's, not a restatement of it.
- **Project structure fully regenerated** by actually listing
  `src/gitten/`, `tests/`, `scripts/`, and `assets/` on disk (`ls`, not
  editing the prior tree) -- confirmed stale exactly as the brief warned:
  the previous tree was still missing 13 modules that had shipped since the
  last regeneration (`app_launch.py`, `visible_windows.py`, `mouse_game.py`,
  `mouse_window.py`, `system_idle.py`, `command_bar_hotkey.py`,
  `command_bar_window.py`, `commands.py`, `reminders.py`,
  `settings_window.py`, `dashboard_window.py`, `telegram_lists.py`, and an
  `assets/` entry at all).
- **Roadmap rewritten from a real check**: grepped every `GITTEN_V1_*_SPEC.md`
  for deferred/out-of-scope language (v1.6 through v1.9 turned out to have
  none written in that form -- their scope notes are elsewhere in each
  spec's prose) and cross-referenced this file's own record of what
  actually shipped, rather than assuming the old roadmap was still
  accurate. Two real, substantive changes: **removed** "a full settings
  UI" from the deferred list (resolved by v1.11 -- leaving it would have
  been actively wrong, not just stale) and **added** a new item that
  genuinely is still open and easy to have missed: v1.11 explicitly scoped
  the settings panel to *never* cover badge thresholds/away-timing/the
  hotkey combo/spawn intervals, and separately, `command_bar_hotkey.py`'s
  own code comment (confirmed by reading the file directly) still says
  "there's no other way to summon it yet" if `RegisterHotKey` fails --
  both genuinely unresolved gaps, not carried forward reflexively. Telegram's
  status was re-confirmed unchanged (still just the standalone script +
  credential/list persistence, `telegram_watcher.py` still doesn't exist)
  and stated plainly rather than left to quietly age out of the roadmap,
  per the brief's explicit instruction.
- **Screenshots**: `assets/demo.png` was left as-is (still accurate, no
  redo needed per the brief). Settings and Dashboard **were** captured as
  real `QScreen.grabWindow` screenshots -- practical in this environment,
  confirmed by the fact that both windows were already screenshotted this
  way during their own v1.11/v1.12 build sessions -- rather than left as a
  TODO. Settings shows the Distraction tab specifically (judged more
  representative of "a real settings UI" for a reader skimming the README
  than the sparser General tab, since it's the one that shows off the
  shared list-editor pattern reused across three of the five tabs);
  Dashboard shows its default view with a real scratch repo's realistic
  ~70-commit history, a real 4-day current streak next to a real longer
  best streak, and two real pending reminders. Saved as `assets/settings.png`
  and `assets/dashboard.png`, referenced inline in the README right where
  each window is described. Generating the dashboard screenshot's scratch
  data hit the exact same reversed-commit-order `git log --since` footgun
  already recorded in section 25 -- fixed the same way (iterate oldest-day-
  first), rather than rediscovering it from scratch.
- Also added `GITTEN_HOUSEKEEPING_2_BRIEF.md` to version control, same
  treatment every other spec/brief file in this repo has gotten (see
  section 11/15 for the same pattern).

**Version bump**: `pyproject.toml` was at `0.6.0`, unchanged since the
first housekeeping round bumped it there for v1 through v1.5. Continued the
same "one minor-version step per major round" scheme that round
established rather than inventing a new one: v1.6 through v1.12 is seven
more rounds, so `0.6.0` -> `0.13.0`.

**Testing**: `pytest -q` -> unchanged at **234/234 passed** (no `.py` file
was touched this round -- README/assets/pyproject-version only, confirmed
by `git status` before committing). No other testing applies to a
documentation-only round beyond the screenshot verification described
above.

Committed separately from any code change (there wasn't any this round),
per the brief's explicit instruction, and pushed to `origin/main`.

## 27. v1.13 -- a real design system, applied to Settings & Dashboard

Input is `GITTEN_V1_13_SPEC.md`. Two-part round, in the order the spec
lays out: define `theme.py` first, then apply it to exactly two windows
(Settings, Dashboard) and nothing else. The command bar, the nudge/alert
bubbles, and the cat sprite itself were **not** touched this round, per
the spec's explicit scope -- confirmed after the fact by diffing this
round's changes against `git status`: only `theme.py` (new),
`settings_window.py`, and `dashboard_window.py` changed, plus the two
screenshot assets.

### Part 1: the color audit, before writing a single new value

Grepped this entire codebase for `QColor(`/hex literals before picking
anything, per the spec's explicit "audit before inventing" instruction --
documented directly in `theme.py`'s own module docstring so a future
session can see the reasoning without re-running the grep:

- The cat's own coral body (`sprite.BODY_COLOR` `#E8935F`) -- chosen as
  this round's **primary accent**, verbatim, not a new invented brand
  color, specifically so Settings/Dashboard read as "the same cat's
  control panel" rather than a bolted-on separate app.
- The reminder-alert amber (`sprite._ALERT_FILL_COLOR`/`_ALERT_BORDER_COLOR`,
  itself already reused from the low-battery badge color per v1.10) --
  kept as `theme.WARNING_FILL`/`WARNING_BORDER`, unchanged, ready for a
  future round if Settings/Dashboard ever need a warning state (none does
  yet this round).
- The heatmap's four greens and empty-day gray
  (`dashboard_window._HEATMAP_COLORS`/`_HEATMAP_EMPTY_COLOR`) --
  confirmed as meaningful data encoding and **deliberately left
  untouched**, per the spec's explicit instruction.
- `sprite.OUTLINE_COLOR` (`#2C2C2A`) -- reused verbatim as `theme.
  TEXT_PRIMARY`, so body text in Settings/Dashboard and the cat's own
  linework share one "ink" color instead of the app having two different
  near-blacks living side by side.
- A scatter of one-off badge/accessory colors with no shared home
  (critical-battery red, charging yellow, high-resource blue, disk gray,
  streak-star gold, purr-heart pink, particle gold) and the dark
  translucent overlay backdrops (command bar, inbox panel) -- all noted in
  the audit, none touched, since none of them belong to Settings/Dashboard
  and the overlays are explicitly out of scope this round.

### `theme.py` -- what it actually defines

A `QColor` palette (primary accent + hover/pressed/soft variants, the
reused warning tone, three light-theme surface tones, a border color, two
text colors), `FONT_FAMILY`/`FONT_SIZE_BASE`, spacing constants
(`SPACING_XS/SM/MD`), and **one** standard corner radius (`RADIUS = 8`,
`RADIUS_SM = 4` for small nested elements) used everywhere rather than an
ad hoc number per widget, per the spec's explicit ask. Expressed as a
single QSS string (`STYLESHEET`) covering `QDialog`/`QLabel`/`QTabWidget`/
`QTabBar`/`QPushButton`/`QLineEdit`/`QSpinBox`/`QListWidget`, plus three
small functions: `apply_theme(widget)` (one call per window, QSS cascades
to every child automatically), `mark_primary_button(button)`, and
`mark_muted_label(label)`/`mark_section_header(label)`.

**The primary/secondary button distinction was a judgment call the spec
didn't spell out, worth recording**: giving *every* `QPushButton` a solid
coral fill (Save, Add, Remove, Cancel-per-reminder-row, Close, all at
once) would have read as a wall of identically loud buttons rather than a
considered hierarchy -- the opposite of what a design system is for. Instead,
`QPushButton` defaults to a neutral outlined style, and only the one
genuinely primary action per screen (each settings tab's own Save button)
gets tagged coral via a Qt dynamic property (`QPushButton[primary="true"]`
in the QSS, set via `mark_primary_button`) -- the same idiom used for
`sectionHeader`/`muted` label tagging. Dashboard's "Close" stays neutral
deliberately, since dismissing a read-only view isn't a "primary action"
the way committing an edit is.

### Part 2: applying it

`settings_window.py` and `dashboard_window.py` each gained one
`theme.apply_theme(self)` call plus layout margins/spacing pulled from
`theme.py`'s constants instead of the ad hoc `addSpacing(8)`/`addSpacing(12)`
literals that were there before. Every field/section label across both
windows is now tagged `mark_section_header` (coral, semi-bold) or
`mark_muted_label` (the "Saved." confirmations, the Telegram tab's
explanatory note, empty-state "No pending reminders." text, and the
dashboard's "Commits this week" line, which reads as supporting detail
under the current/best streak headline). The dashboard's cat-name and
current/best-streak numbers gained light inline rich-text emphasis (the
name in the accent color, the streak counts bolded) -- a purely
presentational change to the same underlying values, not new data.

**`_HeatmapWidget` keeps its own green shading logic completely
untouched** (confirmed by diff -- `_shade_for_count`/`_HEATMAP_COLORS`
have zero changes), per the spec's explicit "meaningful data-encoding, not
decoration to be reskinned" instruction. What did change: it now paints a
rounded `theme.SURFACE_INSET` card behind its (unchanged) cells first,
with a small `_CARD_PADDING` margin so the grid doesn't bleed to the
card's edge -- the one new visual addition is purely a themed backdrop,
not a change to how any cell is colored.

**No functional change anywhere -- verified live, not just by reading the
diff**: re-ran both existing live smoke-test scripts from the v1.11/v1.12
sessions (`live_settings_test.py`, `live_dashboard_test.py`) unmodified
except for two things that turned out to be necessary, both recorded
below since they're worth remembering for future live scripts in this
project:

1. **`live_settings_test.py` hung indefinitely on this run** (zero output
   even after 60+ seconds) -- root cause, found by inspection rather than
   guessing: unlike `live_dashboard_test.py` (which pre-seeds `repo/path`
   into `QSettings` *before* constructing `GittenApp`), this script
   constructed `GittenApp()` first and only pre-seeded a scratch repo
   afterward. It had silently worked in every prior run only because
   `QSettings`'s `repo/path` happened to still hold a leftover value from
   earlier testing in the same session; this session started with
   genuinely clean `QSettings` (a good sign, not a bug -- confirms the
   v1.11/v1.12/housekeeping sessions' own cleanup discipline actually
   worked), which meant `GittenApp.__init__` -> `_restore_repo()` -> a
   real, blocking `QFileDialog.getExistingDirectory()` with no monkeypatch
   installed yet and no one there to dismiss it. Fixed the same way every
   other scratch script in this project already does it correctly: seed
   `repo/path` into `QSettings` *before* `GittenApp()` is constructed, not
   after. Worth restating as a standing rule for this project's own live
   test scripts: **always pre-seed `repo/path` before constructing
   `GittenApp` in a non-interactive script**, regardless of whether a
   monkeypatch is coming later for a different purpose.
2. **One assertion in `live_dashboard_test.py` needed updating**, and
   confirmed this was the *expected*, intentional styling change rather
   than a real regression before touching the script: it asserted the
   current/best streak labels' exact plain-text value, which now includes
   the new `<b>...</b>` rich-text tags around the number (see above) --
   updated the assertion to match the new (still value-identical) text
   rather than reverting the styling.

With both fixes applied, **all 21 checks across the two live scripts
passed** (10 in the settings script, 11 in the dashboard script) -- every
Save button, every live-apply path (distraction/focus config pushing into
live in-memory state), every Cancel button, tab switching, reopening, and
both windows' command-bar dispatch (`settings`/`dashboard`) all still work
exactly as before, confirming this was a pure styling pass. `pytest -q` ->
unchanged at **234/234 passed** (no pure-logic module touched).

### Real screenshots, compared side by side against last round's, per the spec's explicit instruction

A live, non-offscreen `GittenApp` had Settings (Distraction tab) and
Dashboard opened and captured via `QScreen.grabWindow`, using the *same*
scratch-repo/reminders setup the last round's screenshots used, so the
comparison is apples to apples rather than differently-staged data. Both
were actually opened and looked at, side by side against the current
`assets/settings.png`/`assets/dashboard.png` from last round (v1.11/v1.12,
default unstyled Qt widgets):

- **Settings**: a warm off-white page background instead of flat system
  gray, a white card with a visible coral-underlined active tab (the
  inactive tabs now clearly recede), coral section-header labels instead
  of identical plain-black text for every field, list widgets sitting on
  a warm inset background instead of stark white-on-white, and one
  unmistakable solid-coral "Save" button per tab instead of an
  identically-styled gray button indistinguishable from "Add"/"Remove."
  Genuinely, clearly more polished -- not a subtle tweak.
- **Dashboard**: the same warm page/card treatment, coral section headers
  for "Commit activity"/"System"/"Pending reminders", the cat's name
  rendered in the accent color, bolded streak numbers, and -- the one
  piece the spec specifically asked to not leave merely "meaningful in
  isolation" -- the heatmap grid now sits inside its own rounded, subtly
  shaded card instead of floating directly on the dialog's bare
  background, so it reads as *part of* the themed window rather than
  pasted on top of it.

**One trade-off noticed and disclosed rather than glossed over, per the
spec's explicit "if anything doesn't clearly read as more polished, say so
plainly" instruction**: the Distraction tab's title list, which
previously showed all 6 shipped defaults without scrolling, now shows 5
with a scrollbar to reach the 6th. Cause: `QListWidget::item`'s new
themed padding (`theme.SPACING_XS` top/bottom, for visual breathing room)
makes each row taller, and that costs more total list height than the
window's own increased size (`_WINDOW_SIZE` was widened from `(440, 520)`
to `(460, 640)` to compensate, but not quite enough for this specific
6-item case) gains back. This is a minor, genuine regression in
information density on one specific list in one specific tab, not
something to declare invisible -- the list is still fully usable (a
completely ordinary, unremarkable scrollbar, not a rendering bug), and
every other aspect of both windows is unambiguously more polished than
before, but this one specific trade-off is recorded here rather than
silently absorbed into "success," per the spec's own standard for this
round.

### Files changed this round

`src/gitten/theme.py` (new), `src/gitten/settings_window.py`,
`src/gitten/dashboard_window.py`, `assets/settings.png`,
`assets/dashboard.png` (both replaced with the newly-styled captures, so
the README -- which references these exact files -- stays visually
accurate rather than showing a stale pre-v1.13 look immediately after this
round). `command_bar_window.py`, `window.py` (the nudge bubble/inbox
panel), and `sprite.py` were **not** touched, confirmed via `git status`
before committing, per the spec's explicit scope.

## 28. Housekeeping: git history cleanup, removed AI attribution trailers

This is a portfolio project, so it should read as the author's own
authorship history rather than showing tooling attribution. All 31
existing commits (from the initial commit through v1.13) had a
`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` and a
`Claude-Session: https://claude.ai/code/...` trailer appended to their
messages; 19 of the 31 had them.

Fixed in two parts:

- **Going forward**: `~/.claude/settings.json` now sets
  `attribution.commit` and `attribution.pr` to empty strings, so future
  commits and PRs stop getting these trailers appended automatically.
- **Existing history**: rewrote every commit message on `main` with
  `git filter-branch --msg-filter` (a small Python filter stripping any
  line starting with `Co-Authored-By: Claude`, `Claude-Session:`, or
  otherwise mentioning "Generated with ... Claude" / a `claude.ai/code`
  link, plus trailing blank lines). This only touched commit message
  text -- trees (diffs), author/committer dates, and commit order were
  verified identical before and after via `git diff --stat` against a
  `backup-before-attribution-cleanup` tag and a full date/subject/order
  diff. Commit hashes changed as an unavoidable consequence of rewriting
  history. Force-pushed the rewritten history to `origin/main` with
  `--force-with-lease` (safe here: solo project, no other collaborators,
  no forks/PRs against the old history). Verified afterward that
  `git log --all` contains no mention of "Claude" anywhere.

## 29. Follow-up: GitHub still showed Claude as a contributor -- checked author/committer identity, found nothing to fix

The `#28` cleanup only rewrote commit message *text* (the trailer lines).
GitHub's Contributors graph is actually keyed off each commit's
Author/Committer identity fields, which are separate from the message
and weren't inspected last time -- so it was worth checking directly
rather than assuming the graph would just catch up.

Ran, across the entire history:

```
git log --all --format='%an <%ae> / committer: %cn <%ce>' | sort -u
```

Result: a single line, `nolimiya <eliyamonazam84@gmail.com> / committer:
nolimiya <eliyamonazam84@gmail.com>`, on every single commit. No
Claude/Anthropic author or committer identity exists anywhere in this
repo's history -- it never did. So there was nothing to rewrite here:
no `filter-branch --env-filter`, no new force-push. What was actually
being seen on GitHub was the Contributors graph still showing cached
data from before the `#28` force-push; GitHub can take a while (up to
about a day, sometimes needing a hard refresh) to recompute that graph
after a history rewrite.

## 30. v1.14 -- the design system, applied to the command bar & every bubble type

Input is `GITTEN_V1_14_SPEC.md`, Phase 2 of the visual-polish plan v1.13
started: apply `theme.py`'s palette to everything still drawn with ad hoc
colors via raw `QPainter` calls -- `command_bar_window.py`'s input panel,
and the two bubble types (`window.py`'s regular nudge/one-liner bubble and
the v1.10 reminder-alert styling) -- without touching the cat/mouse sprite
art itself (Phase 3, a separate future round).

### A scope question worth resolving explicitly before writing any code

The spec's hand-off prompt says "don't touch `sprite.py` this round," but
its own Scope section immediately qualifies that as "the cat/mouse sprite
art itself is Phase 3... don't touch `sprite.py`'s **cat/mouse drawing**
this round" -- and Section 3 explicitly requires re-styling the
reminder-alert bubble (the amber fill, the bold border, the alarm-clock
icon). Checked where that bubble is actually drawn before assuming either
reading: `_draw_speech_bubble`, `_draw_alarm_icon`, `nudge_bubble_size`,
and the `_ALERT_FILL_COLOR`/`_ALERT_BORDER_COLOR` constants all live in
`sprite.py`, not `window.py` (`window.py` only calls into them for layout/
timing -- see the v1.10 bugfix entry in section 22 for how that split came
to be). Grepped `window.py` for any bubble color to be sure it wasn't
sourced there instead -- it isn't. Given that, fulfilling Section 3 at all
*requires* touching `sprite.py`'s bubble-drawing functions; the prohibition
is read here as scoped to the cat/mouse body/face/ears/tail/badges/streak-
icon rendering (everything Phase 3 will eventually reskin), not to the
speech-bubble code that happens to live in the same file. This is a
judgment call, so it's recorded here per this project's own "flag it
plainly rather than ship quietly" standard, not just assumed silently:
**only `_draw_speech_bubble`, `nudge_bubble_size`, `_draw_alarm_icon`, and
the alert/bubble color constants were touched in `sprite.py`** -- diffed
against `git status`/`git diff` before committing to confirm no cat/mouse
drawing function (`paint_kitten`'s body/ears/tail/face branches, badges,
streak icons, particles, mouse sprite) changed a single line.

### Command bar: a genuine re-skin, not just re-sourced constants

`command_bar_window.py`'s backdrop used to be a dark, near-opaque
`rgba(32, 32, 36, 235)` HUD-style panel with a light gray border --
explicitly called out in `theme.py`'s own v1.13 docstring as one of the
colors that round deliberately left untouched. Per the spec's "it currently
doesn't share a visual language with Settings/Dashboard at all," this
became a real visual change, not a same-color relabeling: `_BACKDROP_COLOR`
is now `theme.SURFACE_CARD` (white), `_BORDER_COLOR` is `theme.ACCENT`
(coral) rather than `theme.py`'s resting `BORDER` tone -- deliberately,
since this popup is only ever on screen while its `QLineEdit` already holds
real keyboard focus (it hides itself on `FocusOut`), the same state
Settings' own `QLineEdit:focus` rule turns coral for -- and `_CORNER_RADIUS`/
`_PADDING` now read `theme.RADIUS`/`theme.SPACING_SM` directly (the latter
was already numerically 8, same as before, but now single-sourced instead
of a second hardcoded `8`). The `QLineEdit`'s own small inline stylesheet
(text/selection colors, font) was rebuilt from `theme.TEXT_PRIMARY`/
`theme.ACCENT`/`theme.FONT_FAMILY`/`theme.FONT_SIZE_BASE` via `.name()`
instead of the old hardcoded `white`/`#4a90d9`/`14px`. All of `theme.py`'s
values are used as the plain `QColor`/`int`/`str` module constants directly
in the `QPainter` calls and the small inline QSS string -- not a second set
of hardcoded hex literals that happen to match, per the spec's explicit
instruction.

### Bubbles: new theme-sourced constants in `sprite.py`, colors chosen to widen the alert/regular contrast, not flatten it

Two new small blocks of module-level constants in `sprite.py`, both reading
straight from `theme.py`:

- `_ALERT_FILL_COLOR`/`_ALERT_BORDER_COLOR` now *are* `theme.WARNING_FILL`/
  `theme.WARNING_BORDER` (previously their own independent `QColor("#FFF3E0")`/
  `QColor("#FB8C00")` literals that merely happened to equal what `theme.py`
  also independently hardcoded -- exactly the "two sources of truth that
  could silently drift apart" risk the spec's Important Constraint warns
  about). Numerically unchanged, now structurally impossible to drift.
- New `_BUBBLE_FILL_COLOR = theme.SURFACE_CARD`, `_BUBBLE_BORDER_COLOR =
  theme.BORDER`, `_BUBBLE_TEXT_COLOR = theme.TEXT_PRIMARY`,
  `_BUBBLE_PADDING_X = theme.SPACING_SM`, `_BUBBLE_PADDING_Y =
  theme.SPACING_XS` replace the regular bubble's old flat-white fill +
  near-black (`OUTLINE_COLOR`) 1.6px border + hardcoded `8.0`/`5.0` padding.
  The regular bubble's border also thinned from 1.6px to 1.2px to read as
  the same soft, light-bordered "card" convention Settings' `QLineEdit`/
  `QListWidget` already use, rather than the old bold black comic-panel
  outline.

**This was a deliberate design choice, not an oversight, and it's the
opposite of the risk Section 3 warned about**: softening the *regular*
bubble's border while leaving the alert bubble's bold, saturated amber
border untouched makes the two types *more* visually distinct side by
side than before, not less -- confirmed numerically (see Testing) rather
than assumed. Nothing about applying the shared palette here flattened the
two bubble types toward the same look, so there is no "worth flagging as a
regression" case to raise for Section 3, unlike v1.13's list-scrollbar
trade-off.

The font-family string in both `nudge_bubble_size` and `_draw_speech_bubble`
now reads `theme.FONT_FAMILY` instead of a second hardcoded `"Segoe UI"`
literal (still 9pt in canvas units -- `theme.FONT_SIZE_BASE` (13) is a real-
pixel size tuned for Settings/Dashboard's actual `QDialog`s and would be
wildly oversized against this bubble's 128-unit canvas, so it was
deliberately *not* substituted in, per the spec's "the same values" intent
rather than its letter -- pulling in a real-pixel constant here would be a
regression, not a re-skin). The corner radius (`6.0`, `drawRoundedRect`) and
the alert-only entrance/fade timing constants (`_ALERT_POP_SECONDS`,
`NUDGE_DURATION_SECONDS`, `REMINDER_NUDGE_DURATION_SECONDS`) were left
untouched -- the spec calls out "color/spacing constants" for bubbles
specifically (radius/timing aren't mentioned, unlike the command bar's
explicit "palette, corner-radius, and spacing"), and Section 2 explicitly
requires preserving the existing entrance/fade timing exactly.

### A live-screenshot capture technique note worth recording for future sessions

`QScreen.grabWindow(window.winId())` against this project's translucent,
layered, frameless top-level windows (`KittenWindow`, `CommandBarWindow`)
came back **solid black** in this sandboxed session, even though the same
call against a plain opaque `QLabel` worked correctly and `grabWindow(0)`
(the full screen) correctly captured real, normally-composited desktop
content (confirmed with a throwaway comparison script before trusting
either result). This is the same category of "layered/topmost window
screenshot quirk in this particular sandbox" already recorded in this
file's very first debugging section (see section 4) -- that session
abandoned live-window screenshots entirely in favor of off-screen
`QPixmap` renders; this session found a workaround instead, since the spec
explicitly requires a real live capture: **grab the full screen
(`grabWindow(0)`) and crop to the target window's `frameGeometry()`,
scaled by `screen.devicePixelRatio()`**, rather than grabbing the window
directly. This produced correct, real screenshots for all three captures
below. Worth trying first, before falling back to off-screen rendering, in
any future session that needs to screenshot one of this app's own
translucent top-level windows live.

### Testing

- `pytest -q` -> unchanged at **234/234 passed** (no pure-logic module
  touched -- this is `QPainter`/QSS styling only).
- **Live, real screenshots**, via a scratch script (`live_v14_test.py`,
  scratchpad-only, not committed) that constructed a real, non-offscreen
  `GittenApp` against a real scratch git repo (repo/path pre-seeded into
  `QSettings` before construction, per the standing rule v1.13's dev notes
  already recorded) and used the full-screen-crop technique above:
  - The command bar (`_show_command_bar()`), captured while genuinely
    focused and visible: a white rounded card with a coral border and
    dark placeholder text, immediately recognizable as the same family as
    Settings' `QLineEdit`/Save-button coral, next to the cat.
  - A regular nudge (`window.show_nudge("Commits today: 1")`): a soft
    white bubble with a thin, light border and near-black text -- reads as
    a themed card now, not the old bold black-outlined comic bubble.
  - **A real, live-triggered reminder alert**: `_dispatch_command("remind",
    "2s take a break")` through the actual command-dispatch path, then the
    process was pumped for ~9.5s (past the real ~7s `SYSTEM_SAMPLE_INTERVAL_MS`
    tick, no manual `show_nudge` call) until `window._nudge_alert` was
    confirmed `True` and `window._nudge_text == "take a break"` from the
    real reminder machinery, then captured: a bold amber-bordered, amber-
    filled bubble with bold text and the small ringing alarm-clock icon,
    clearly and immediately distinguishable from the regular nudge
    screenshot above sitting right next to it.
  - `tasklist` confirmed no stray `python.exe` processes after the script
    exited (it never calls `app.exec()`, matching this project's existing
    live-script convention).
- **Numeric distinctness check**, the same standard section 22 already
  held itself to: rendering the same text (`"take a break"`) through
  `_draw_speech_bubble` with `alert=False` vs `alert=True` off-screen and
  diffing every pixel came back **3,617 differing pixels out of 13,200**
  (~27%) -- confirms the two bubble types remain a substantial, genuine
  visual difference after the re-skin, not a subtle tweak that only reads
  as distinct by chance of eyeballing.
- Confirmed both (a) the command bar and both bubble types now visually
  belong to the same white/warm-card, coral-accent, light-border family as
  `assets/settings.png`, and (b) the reminder alert is still unmistakably
  more urgent than the regular nudge side by side -- both true, nothing to
  disclose as a regression this round.

### Files changed this round

`src/gitten/sprite.py` (bubble-drawing functions and alert/bubble color
constants only -- confirmed via diff that no cat/mouse drawing function
changed), `src/gitten/command_bar_window.py`. `window.py`, `settings_window.py`,
`dashboard_window.py`, and every other cat/mouse-drawing part of `sprite.py`
were **not** touched, confirmed via `git status` before committing.

## 31. v1.15 -- the cat/mouse art, redrawn in a bold flat mascot style

Input is `GITTEN_V1_15_SPEC.md`, Phase 3 (the last) of the visual-polish
plan: replace the original v1 soft/glossy cat and mouse art with a bold,
flat mascot look -- one uniform outline color/width everywhere, flat
single-tone fills with no gradients, and the cat's own body color folded
into `theme.ACCENT` itself. Every pose and animation timing had to stay
exactly as before; only the drawing style changes. Built and verified in
the spec's own 5-part order, each part checked with a real screenshot
before moving on, exactly as instructed.

### Shared infrastructure, set up once in Part 1

- `OUTLINE_COLOR` is now `theme.TEXT_PRIMARY` and `BODY_COLOR` is now
  `theme.ACCENT` -- both numerically unchanged from their old independent
  hex values (`theme.py`'s own v1.13 docstring already documented reusing
  these exact values verbatim), so this is a single-sourcing change, not a
  new color. `theme.py`'s `ACCENT` definition got a short note added
  pointing out the relationship now runs the other way (`sprite.BODY_COLOR`
  imports from `theme`, not the reverse) so a future reader isn't confused
  by the v1.13 docstring's original phrasing.
- `_OUTLINE_PEN_WIDTH` bumped from 2.6 to 3.2 and, unlike before, is now
  used unmodified at almost every call site in the main character's own
  drawing code -- the old code passed a different width into nearly every
  single `_outline_pen(...)` call (2.2, 2.4, 1.8, 2.0, 1.6, 1.4...); every
  one of those per-element overrides was removed this round, per the
  spec's explicit "not varying stroke weights per element" instruction.
- `BODY_HIGHLIGHT` (the gradient's light stop) and `INNER_EAR_COLOR` are
  gone. Two-tone details that used to lean on a highlight gradient (inner
  ears, the nudge-wave paw, the high-five paw pad) now use a new flat
  `SECONDARY_FILL_COLOR = theme.ACCENT_SOFT` -- one of `theme.py`'s own
  existing plain constants (its "accent lightened toward white" variant)
  rather than a new one-off hex invented just for this file.
- A new `_draw_flat_eye_arc(painter, ex, ey, half_width, bulge, thickness)`
  helper draws a bold, flat-**filled** crescent between two quadratic
  curves -- the mascot-style replacement for the old thin single-stroke
  closed-eye curve. Shared by every closed/squinted eye pose (idle, happy,
  purr, deep sleep, and the sulking peek), each just passing a different
  `bulge`/`thickness`/`half_width`, so all of them read as the same bold
  shape language instead of each pose inventing its own curve. This is
  also the piece that most directly answers the spec's "flat-filled,
  bold-outlined... not tiny highlight dots, thin soft curves" instruction.

### Part 1 -- body/ears/tail base shape + neutral idle, verified first

`_draw_body` lost its `QRadialGradient` entirely -- a single flat
`painter.setBrush(fill_color)` -- per the spec's explicit "this is an
intentional style change, not something to preserve out of habit."
Night-mode blending (`_blend_color`) now only blends the one flat body
color toward the moonlit tone; there's no separate highlight color left to
blend a second time.

**The tail needed a real technique change, not just a color swap, to
actually gain a genuine outline**: the old tail was a thick `BODY_COLOR`
line stroke with a *second*, thin dark stroke traced down its own
centerline -- which reads as a decorative seam, not a silhouette outline
(an outline has to run along a shape's edges, not through its middle).
Confirmed by literally looking at the old `assets/demo.png`'s "Purring"
panel before touching the code: yes, that faint line down the tail was
always a centerline seam, never an edge outline. Fixed with the standard
"stroke behind fill" trick for turning a line into an outlined shape: the
same path is stroked twice, once wider in `OUTLINE_COLOR` underneath, once
at the tail's own width in `BODY_COLOR` on top.

**A real bug this technique change surfaced, caught by actually looking at
a live screenshot of the AWAY pose, not just the regular swaying tail in
isolation**: the v1.8 AWAY pose's *curled* tail variant has its path's two
endpoints only ~9 canvas units apart. With the new, much wider outline
stroke and `RoundCap` line ends, the two end caps overlapped into one
solid blob that swallowed the curl shape entirely and partly covered the
closed eye next to it -- confirmed visually in both a live
`grabWindow`-crop screenshot and a clean off-screen render before
believing it was fixed. Two changes were needed together, not just a
smaller number: (1) `_TAIL_OUTLINE_EXTRA` (how much wider the outline pass
is than the fill) is a separate, smaller constant (2.4) rather than
`_OUTLINE_PEN_WIDTH * 2`, since a literal "same width as every other
shape" ring made the short curled path's round caps dominate; (2) the
curled path's own control points were widened and moved lower/further back
along the lying body (away from the face) so its two endpoints sit ~16
units apart instead of ~9 -- confirmed by re-rendering after each change,
not assumed fixed from the math alone. The regular swaying tail (whose
endpoints were always well separated) needed no geometry change, only the
outline technique.

`_draw_idle_face` was rebuilt on `_draw_flat_eye_arc`; the mouth stayed a
bold stroke (mouths in this style read fine as simple bold strokes -- the
"flat-filled" instruction was primarily aimed at the eyes, which is where
the old "tiny highlight dots, thin soft curves" detail actually lived).

**Verified live, per the spec's explicit instruction, before touching
anything else**: `KittenWindow.set_mood(Mood.IDLE)`, screenshotted via the
v1.14-documented full-screen-grab-and-crop technique. Confirmed a flat
coral body, a genuinely outlined tail, and bold flat crescent eyes, clearly
reading as a different, bolder style than the old `assets/demo.png` side
by side.

**A real screenshot-environment quirk found and worth recording**: the
live screenshot's body color rendered as a desaturated brown/tan instead
of the expected coral. Chased down before assuming a code bug: an
off-screen `QPixmap` render (bypassing the OS display compositor entirely)
sampled the exact same body pixel at precisely `#E8935F` -- proving the
*rendered* color is correct and the live screenshot's tint is a capture-
path artifact, not a rendering bug. This machine's registry has a
`bluelightreduction.settings` value present (consistent with, though not
conclusively proving, Windows Night Light being active in this sandboxed
session), which would explain a live full-screen grab picking up a warm
color shift that an in-memory off-screen render never passes through.
**Net effect on verification going forward this round**: live screenshots
remained the primary check for shape, pose, and text/font rendering (per
the spec), but color-accuracy claims were cross-checked against an
off-screen render's exact sampled pixel value rather than trusted from a
live screenshot's screen-composited tint alone -- the same "verify a claim
the way it can actually be verified, don't just eyeball one imperfect
channel" discipline this project's dev notes already model elsewhere (e.g.
section 4's zombie-process detour, section 12's offscreen-fonts finding).

### Part 2 -- happy, waiting, deep-sleep faces

`_draw_happy_face`'s eyes moved onto `_draw_flat_eye_arc` with a negative
`bulge` (curves upward, reading as a happy squint, mirroring idle's
downward-curving crescent). `_draw_waiting_face`'s eyes/pupils/brow/mouth
already used the bolder "filled white circle + solid pupil" idiom from the
start (this pose was always closer to "flat filled bold" than the
closed-eye poses were) -- just needed every custom pen width unified to
the shared default and the pupil bumped slightly larger to match the new
bolder weight. `_draw_sleep_face` (the v1.8 AWAY deep-sleep face) moved
onto `_draw_flat_eye_arc` with a near-zero `bulge`, reading as a "more
fully shut" bold sliver, distinct from idle's more open crescent -- the
same distinction the old flat-line-vs-curve treatment was going for,
carried into the new shape language.

**Verified live**: `set_mood(HAPPY)`, `set_mood(WAITING)`, and
`set_away(True)` each screenshotted in turn. The AWAY pose's tail-blob bug
described above was caught during *this* part's live check (checking the
deep-sleep face incidentally required rendering the curled tail for the
first time this round) and fixed before moving on, per the spec's
"verify... before moving to the next part" discipline -- not carried
forward as a known issue.

### Part 3 -- interaction poses: sulking, purr, high-five (plus focused/curious)

The spec's own Part 3 list names "the sulking/reconciliation stages, the
hover-purr face, the high-five pose" specifically; `focused`
(test/build-running reaction) and `curious` (v1.6 new-app reaction) aren't
named in that list but are the same category of thing (a standalone
interaction/reaction overlay, not a mood face or a piece of chrome) and
were folded into this same part rather than left stranded between Part 2
and Part 4.

- `_draw_purr_face`: eyes onto `_draw_flat_eye_arc` with a squint-scaled
  `bulge` (the existing `squint` sine value now drives the crescent's
  depth instead of a stroked curve's control-point offset), mouth stroke
  unified.
- `_draw_focused_face` / `_draw_curious_face`: both already used the bold
  filled-circle-eye idiom; just unified every custom pen width to the
  shared default and enlarged the pupils to match.
- `_draw_face_turned` (the sulking stages): the seam line and stage 1-3
  partial eye reveal both moved onto the shared outline width/the
  `_draw_flat_eye_arc` helper (scaled by the existing `reveal` fraction),
  so a mid-sulk peek reads as the same bold crescent shape as every other
  closed-eye pose, just partially revealed.
- `_draw_high_five_paw` / `_draw_nudge_wave` (the paw/wave overlays,
  drawn regardless of mood/pose): switched from the removed
  `BODY_HIGHLIGHT` to the new flat `SECONDARY_FILL_COLOR`, uniform outline.

**Verified live** (`set_attention(SULKING, 0)`, `set_attention(SULKING,
3)`, a real `enterEvent` via `_hovering = True` for purr, and
`_high_fiving = True` for the paw overlay) plus an off-screen contact
sheet for a cleaner side-by-side look at all four (and `focused`/`curious`
separately) than the live desktop's own background clutter allowed for at
this small a crop. All read as bold, consistent, and distinct from each
other -- sulking stage 3 and purr look similar to each other (both are a
near-full-face closed-eye crescent + smile), which was already true of the
pre-v1.15 art and isn't something this round's restyling was asked to
change (the two are never shown at the same time in practice, unlike the
purr-vs-focused/curious-vs-focused precedence pairs this codebase's v1.5/
v1.6 dev notes specifically verified with pixel-diffs, which *can* co-occur
and so actually need to look different).

### Part 4 -- status badges, streak star/crown, seasonal accessories

None of these small icons had a gradient to remove (they were already
flat-filled) except the birthday party hat's three-stop `QLinearGradient`
rainbow cone, replaced with one flat `_PARTY_HAT_COLOR` (`#42A5F5`) --
gradients are gone everywhere in this file now, not just on the body.

**A genuine scale tradeoff, decided deliberately and documented rather
than silently picking one number**: applying the character's own
`_OUTLINE_PEN_WIDTH` (3.2) literally to these much smaller icons (some, like
the lightning bolt, only ~6 canvas units across) would swallow them into
unrecognizable blobs -- confirmed by actually rendering one at that width
before deciding against it. A second shared constant,
`_SMALL_ICON_OUTLINE_WIDTH = 1.6`, is used uniformly across every badge,
the streak star/crown, and every seasonal accessory instead -- still a
real, uniform bump from the old per-icon range of 1.0-1.2 (a different
value nearly every time), and still exactly *one* width for this whole
tier of chrome, holding to the spec's "not varying stroke weights per
element" instruction at a second, smaller scale appropriate to these
icons' size rather than literally reusing the main character's own number.

**Verified live** (`set_badge`, `set_streak`, `set_accessory` cycled
through several combinations) plus an 11-panel off-screen contact sheet
covering every badge, all three streak tiers, and all three accessories at
once for a clean, uncluttered look at every small icon side by side --
all bold, legible, and consistent with each other.

### Part 5 -- the mouse sprite

Same style rules, applied at the mouse's own smaller 64-unit canvas (half
the cat's 128): `_draw_mouse_body` lost its `QRadialGradient` for a flat
`_MOUSE_BODY_COLOR` (`#AEB4BD`, a cool flat slate gray -- picked so the
mouse still reads as clearly "not the cat" at a glance, per the spec's
"its own small palette choice is your call"). The mouse's ears now use the
cat's own `SECONDARY_FILL_COLOR` rather than a second gray-highlight tone,
a deliberate small touch tying the two sprites into one shared palette
family rather than two unrelated color schemes, per the spec's "should
read as belonging to the same visual world as the restyled cat." The tail
got the same "wider outline stroke underneath, narrower fill stroke on
top" treatment as the cat's own tail, so it gains a real silhouette outline
instead of the old plain, unoutlined single stroke.

**Outline width was scaled, not copied verbatim, and this is deliberate**:
`_MOUSE_OUTLINE_WIDTH = _OUTLINE_PEN_WIDTH * (MOUSE_CANVAS / CANVAS)` --
exactly half the cat's own width, matching the mouse canvas's exact
half-scale, so the *relative* boldness matches the cat instead of the
*absolute* number (which would read twice as heavy, proportionally, on
the smaller sprite).

**Verified live**: a real `MouseWindow.show_at(...)`, screenshotted via the
same crop technique, plus a clean off-screen render. Reads as a small,
bold, flat companion creature that clearly belongs next to the restyled
cat -- round slate body, peachy ears matching the cat's own inner-ear/
paw-pad tone, bold outlined tail, solid dot eyes.

### `assets/demo.png` regenerated

Same 6-panel composition as the existing image (Happy+Low Battery,
30-Day Streak, Birthday, Purring, Sulking, Curious) for an apples-to-apples
before/after comparison, regenerated via the same off-screen-`QPixmap`
technique used originally -- run on the real `windows` Qt platform plugin
rather than `QT_QPA_PLATFORM=offscreen`, per the v1.6-era lesson recorded
in section 17 (offscreen has zero installed fonts, so any drawn text comes
out as tofu boxes; this image's own panel labels are drawn text). Comparing
it side by side against the pre-v1.15 image: every panel now shows a flat
coral body with no glossy highlight, a uniformly bold outline on every
shape including the tail (which now has a real visible ring around its
silhouette instead of no outline at all), and bold simplified crescent
eyes instead of thin soft curves -- genuinely, clearly a different,
bolder style, not a subtle palette tweak. Saved over the existing
`assets/demo.png`; `README.md` already references this exact filename with
no hardcoded dimensions in its text, so no README changes were needed.

### Does this genuinely read as one cohesive, improved character across every pose? Yes, with one honest caveat

Every pose shares the same outline color/width (at its own appropriate
scale), the same flat-fill discipline, and the same crescent-eye shape
language for every closed/squinted expression -- side by side, the whole
set reads as one consistent design system applied to one character,
clearly more polished than the old soft-gradient look, matching this
project's own "declare success only if it's actually true" standard from
v1.13/v1.14. **The one caveat, disclosed rather than smoothed over**:
sulking stage 3 and the purr face are visually quite similar to each
other now (both a near-full-face bold closed-eye crescent + smile) --
this was already true before this round's restyling and the spec never
asked this round to address it (the two poses are never shown
simultaneously, unlike the hover/focused/curious triple this codebase has
specifically pixel-diff-verified as needing to be distinguishable from
each other), so it wasn't treated as a defect to fix, but it's recorded
here rather than left unmentioned.

### Testing

`pytest -q` -> unchanged at **234/234 passed** throughout (this is pure
`QPainter` drawing code with no branching logic worth unit testing in
isolation, the same standard `sprite.py` has always been held to -- see
section 12's Feature 3 for why this file has never had a `test_sprite.py`).
Every part above was verified with a real, non-offscreen `KittenWindow`/
`MouseWindow`, screenshotted via the full-screen-grab-and-crop technique
v1.14's dev notes documented for this sandbox's `grabWindow(winId)`-comes-
back-black limitation (confirmed still necessary and still working, so
that workaround didn't need re-discovering), plus off-screen `QPixmap`
contact sheets for cleaner side-by-side comparisons than the live
desktop's own background clutter allowed at small crop sizes. `tasklist`
was checked clean after every live script run. All scratch scripts and
screenshots were kept out of the repo (scratchpad-only), per this
project's standing convention.

### Files changed this round

`src/gitten/sprite.py` (every cat/mouse drawing function; the bubble/
alarm-icon code from v1.14 was deliberately left untouched, confirmed via
diff), `src/gitten/theme.py` (a small docstring note on `ACCENT`, no value
change), `assets/demo.png` (regenerated). `window.py`,
`command_bar_window.py`, `settings_window.py`, `dashboard_window.py` were
**not** touched, confirmed via `git status` before committing.

## 32. Housekeeping: README touch-up for the v1.13-v1.15 visual-polish arc

Input is `GITTEN_HOUSEKEEPING_3_BRIEF.md`. A lighter round than the
section-28-era README overhaul -- a touch-up, not a rewrite. Read sections
27, 30, and 31 above (the three visual-polish rounds) before writing
anything, per the brief.

Checked README.md for stale appearance wording first, per the brief's
"if the feature list or 'how it's built' section describes the cat's
appearance anywhere (soft/glossy, gradients, etc.), update it" instruction
-- grepped for "soft", "glossy", "gradient", and "pixel-style" and found no
matches anywhere in the file, so there was no stale wording to fix there.
(`pyproject.toml`'s own `description` field still says "pixel-style
kitten," which was already inaccurate before this round and is out of this
brief's stated scope -- README.md only -- so left untouched rather than
scope-creeping into a second file the brief didn't name.)

Added the one thing that actually was missing: a short two-sentence
mention of the shared design system in the "How it's built" section, right
after the existing paragraph about pure-logic layers being unit-testable --
naming `theme.py`, that the cat's coral body color is the primary accent,
and that the sprite/command bar/every bubble/Settings/Dashboard all now
read from the one palette instead of inventing their own colors. Also
noticed `theme.py` itself was missing from the Project Structure file
listing entirely (added in v1.13, never added to that list across three
rounds of edits) -- added it in its alphabetical position with a one-line
description, since a project-structure listing missing a real, load-bearing
module is exactly the kind of staleness this touch-up exists to catch, even
though the brief's three bullet points didn't name it explicitly.

Version bumped `0.13.0` -> `0.16.0` in `pyproject.toml`, following this
project's existing convention of one version-number bump per
`vX.Y`-numbered round since the last housekeeping bump (the `81c7a12`
housekeeping commit bumped `0.6.0` -> `0.13.0` to cover v1.6 through v1.12;
this bump covers v1.13, v1.14, and v1.15 the same way).

No code changed this round -- `README.md` and `pyproject.toml` only, so
`pytest -q` wasn't expected to move and wasn't re-run for this round.

### Files changed this round

`README.md`, `pyproject.toml` (version only).

## 33. v1.16 -- a genuine pixel-art redesign (Phase 4)

Input is `GITTEN_V1_16_SPEC.md`, the last phase of the visual-polish plan:
fully replace v1.15's bold-flat-*vector* mascot style (smooth
`QPainterPath` shapes, one uniform outline width/color) with real pixel
art -- a small, fixed logical grid of flat-filled squares per pose,
upscaled with nearest-neighbor scaling, animated via a small number of
discrete frames instead of continuous sine-driven breathing/swaying. Per
the spec's explicit instruction, read section 31 (v1.15) in full first,
since this round replaces that style rather than layering on top of it.
Built and verified in the spec's own order: Part 0 (the technical
foundation) in complete isolation first, then the 5 pose parts in order,
each checked with a real render before moving on.

### Part 0: the rendering engine, verified before any real pose existed

New module `src/gitten/pixelart.py` -- the one shared engine every pose in
`sprite.py` builds on, the same "shared infrastructure built once, reused
everywhere" discipline `theme.py` and `particles.ParticleSystem` already
established for their own concerns:

- A **frame** is a `tuple[str, ...]` -- one character per logical pixel,
  `.` for transparent, any other character a key into a small per-sprite
  **palette** (`dict[str, str]`, character to hex color). This is the
  spec's own suggested "small 2D grid where each cell maps to a color"
  technique, written directly as Python literals in `sprite.py` -- a
  standard, general pixel-art authoring convention, not tied to or
  reproducing any specific existing project's own tooling or sprites, per
  the spec's explicit originality note.
- `render_frame(frame, palette)` draws one frame to an off-screen `QImage`
  at its own logical grid resolution (one image pixel per grid cell), flat
  fills only, no anti-aliasing -- cached by `(frame, palette)` since the
  actual (frame, palette) space used in a steady-state paint loop is small
  (a handful of poses x at most a couple of palette variants each, e.g.
  day/night).
- `draw_pixel_image(painter, image, rect)` scales that image up to fill an
  arbitrary rect using **`Qt.FastTransformation`** (nearest-neighbor), and
  additionally turns off the painter's own `SmoothPixmapTransform` render
  hint for the draw call -- both matter: pre-scaling the pixmap with the
  fast-transformation flag *and* disabling the painter's own smoothing hint
  for the actual `drawPixmap`, since a smoothing-enabled painter can still
  soften an already-crisply-scaled pixmap when it's composited through a
  further transform (this codebase's own outer `painter.scale()` for
  canvas-unit-to-device-pixel mapping).
- `frame_index(t, num_frames, frame_seconds)` -- the one shared
  discrete-animation convention every pose's own timer reuses, instead of
  each pose inventing its own frame-cycling math.

**Verified in isolation, before writing a single real pose**, per the
spec's explicit "build and verify this first, on the simplest possible
test case" instruction, two ways:

1. A deterministic pixel-exactness check (not just eyeballing an image): a
   2x2 placeholder grid (`RG`/`GB`) rendered, then scaled 100x per logical
   pixel via `draw_pixel_image`, then sampled at the center of each of the
   four resulting quadrants -- every sample came back an *exact* palette
   color (`#ff0000`/`#00ff00`/`#00ff00`/`#0000ff`), and a full horizontal
   sweep across the boundary between two cells showed **exactly one hard
   transition** between exactly two distinct colors, not a gradient ramp.
   This is strictly stronger evidence than "the picture looks blocky" --
   it rules out any residual smoothing at any stage of the scale pipeline.
2. The resulting scaled PNG was also opened and looked at directly: a
   perfectly crisp 2x2 checkerboard with hard, right-angle edges between
   the four color blocks, no blur anywhere.

Only after both passed did any real cat/mouse pose get built.

### Grid size, palette, and frame-timing decisions

- **32x32 for the cat, 16x16 for the mouse/small chrome** -- the spec's own
  suggested sizes, kept as-is after confirming (Part 1) that 32x32 leaves
  enough resolution for legible ears/tail/face detail on the most-seen
  pose. Badges/streak icons/seasonal accessories share the mouse's 16x16
  grid rather than the cat's 32x32 -- the same "these can't take the main
  character's own proportions literally" lesson v1.15's own Part 4 already
  learned for its outline width (a full-scale grid would either vanish a
  ~12-canvas-unit icon into 1-2px slivers, or force an oversized outline),
  applied here to grid *resolution* instead of stroke width.
- **A four-color palette per sprite** (outline, body, a secondary tone for
  inner-ear/paw-pad detail, and white), within the spec's "roughly 4-6
  colors" budget -- `theme.ACCENT`/`theme.ACCENT_SOFT`/`theme.TEXT_PRIMARY`
  reused verbatim as the body/secondary/outline colors respectively,
  continuing v1.15's own "the character's colors are single-sourced from
  `theme.py`" discipline rather than resetting it. Night-mode tinting still
  goes through the existing `_blend_color` helper, just applied to the
  palette's one `"B"` entry now instead of a vector fill color.
  Small-chrome icons (badges/streak/accessories/heart/exclaim/paw) each get
  their own small dedicated palette instead of being limited to the cat's
  four colors -- a witch hat needs black+purple, a pomegranate needs
  red+green, and so on -- still a small, deliberate palette per icon, just
  not literally the cat's own set.
- **One shared frame-timing convention** (`pixelart.frame_index`), but a
  different `frame_seconds` per pose tuned to how that pose used to
  animate continuously: idle/happy breathe+blink at a slow 1.4s/frame,
  purr's "vibration" squint at a brisk 0.45s/frame, the waiting mood's
  nervous glance at 0.6s/frame (replacing what used to be a continuous
  side-to-side sine), away's deep-sleep breathing at a slow 3.0s/frame.
  Each is a judgment call translating a specific old continuous speed into
  a specific new discrete cadence, not one global constant applied
  everywhere.
- **A dynamic `"F"` palette character** for anything that used to be a
  runtime-computed color (a battery badge's own color + alpha pulse, a
  streak tier's gray/gold) -- resolved to an actual hex/alpha string at
  paint time and merged into that call's own palette dict, the same idiom
  `_cat_palette`'s night-tint swap already uses for `"B"`. **A pulsing
  alpha value is rounded to 2 decimal places before it enters the palette
  dict** specifically so `pixelart.render_frame`'s cache (keyed on
  `(frame, palette)`) doesn't mint a brand-new `QImage` on nearly every
  single frame of a continuously-varying pulse -- documented directly in
  both `pixelart.py`'s own cache docstring and at each call site, since
  it's exactly the kind of thing a future session could silently regress
  by inlining an unrounded value.

### Compositing technique: each frame is one full 32x32 grid, hand-composed in the old vector code's own z-order

Rather than a separate transparent image per body part re-composited at
paint time (extra complexity for no real benefit at this scale), each pose
is baked as **one complete 32x32 grid** at design time, built by stamping
tail, then ears, then the body last (so the body's later fill covers both
the tail's root and the ears' base), then the face on top -- the exact same
back-to-front order the v1.15 vector code always drew in, just executed
once per pose during authoring instead of every paint call. This is why a
pixel-art ear still reads as "growing out of the head" and a pixel-art tail
still reads as "rooted at the flank," the same effect the old code got from
its own draw order.

All poses share one fixed grid-to-canvas mapping
(`_CAT_GRID_PX`/`_CAT_ANCHOR_COL`/`_CAT_ANCHOR_ROW`) since every frame was
authored into the same absolute 32x32 coordinate space regardless of where
that particular pose's body happens to sit within it (e.g. the AWAY pose's
lying body sits a little lower in the grid than the sitting poses' body,
but the anchor point is still the same fixed grid cell for every pose) --
one shared mapping, not a per-pose special case.

### Part-by-part build order and verification

Mirrored v1.15's own sequencing exactly, per the spec's explicit
instruction, each part checked with a real render before moving to the
next -- **both** an off-screen `QPixmap` contact sheet through the actual,
shipped `paint_kitten`/`paint_mouse` functions (not a synthetic prototype;
run on the real `windows` Qt platform plugin, not `QT_QPA_PLATFORM=
offscreen`, per the v1.6-era tofu-box-font lesson in section 17) **and** a
real live, non-offscreen `KittenWindow`, screenshotted via the
full-screen-grab-and-crop technique v1.14/v1.15's dev notes documented for
this sandbox's `grabWindow(winId)`-comes-back-black limitation:

1. **Body/idle pose.** Grid technique, palette, and a 2-frame breathe+blink
   idle animation, gotten right on the single most-seen pose first --
   confirmed via both an off-screen render and a live `KittenWindow` with
   `set_mood(IDLE)` before touching any other pose.
2. **Happy, waiting, deep-sleep (AWAY) faces.** Confirmed live via
   `set_mood(HAPPY)` and `set_away(True)` (the deep-sleep face is only ever
   shown paired with the AWAY pose's lying body/drooping ears/curled tail,
   same as v1.15's own Part 2 -- see that section for why building them
   together is necessary, not just convenient).
3. **Interaction poses**: sulking stages 0-3, purr, focused, curious, plus
   high-five's paw overlay (named explicitly in the spec's Part 3 list).
   Confirmed live via `set_attention(SULKING, 2)` and `_hovering = True`
   for purr; focused/curious/high-five confirmed via the off-screen
   contact sheet (`verify_real_sheet.png`, scratchpad-only, not committed)
   since none of those needed a dedicated live capture beyond what the
   contact sheet already showed clearly.
4. **Small chrome**: every status badge, both streak-star tiers, the
   crown, and all three seasonal accessories, at their own dedicated 16x16
   grid scale (see above) rather than the cat's 32x32.
5. **The mouse sprite.** Its own 16x16 grid, 2-frame breathing cycle, same
   z-order compositing technique (tail, then ears, then body last) as the
   cat's own.

**A concrete, deterministic check that the animation is genuinely
discrete, not just "looks blocky at a glance"**: `pixelart._image_cache`
was cleared, then a real `paint_kitten(..., mood=IDLE)` was rendered at 200
different `t` values (`t = 0.0, 0.05, 0.1, ... 9.95`) and the cache size
checked afterward -- **exactly 2** entries, confirming only the two actual
idle frame grids were ever rendered, no matter how many distinct timesteps
were sampled. (An earlier, cruder version of this check instead hashed the
*full* rendered image at each timestep and got 60 distinct hashes out of
60 samples -- initially alarming, but it was checking the wrong thing: the
cat's overall on-screen position still bobs/jitters continuously by design
(explicitly allowed to stay continuous per the spec's "what does NOT need
to change" note), so the *composited* image legitimately differs at every
sub-pixel offset even though only 2 underlying frame grids exist. The
`_image_cache`-size check above is the correct way to verify frame-level
discreteness independent of continuous position animation layered on top
of it -- worth remembering for any future session tempted to reach for a
whole-image hash instead.)

### Judgment calls, recorded rather than made silently

- **"Curious"'s head-tilt is faked without ever rotating the bitmap.**
  v1.15 (and v1 before it) rotated the ears+face via `painter.rotate()` for
  this reaction. Rotating an already nearest-neighbor-scaled pixel image by
  a few degrees would re-introduce smoothed, non-axis-aligned edges right
  where the whole point of this round is to avoid exactly that. Instead,
  the tilt is baked directly into the curious pose's own single frame: one
  ear taller and shifted, the other lower, an asymmetric head silhouette
  that reads as "cocked to one side" without any rotation transform at all
  -- a genuine, standard pixel-art technique for this, not a workaround.
- **The streak star's "twinkle" changed from a continuous radius pulse to a
  continuous alpha pulse.** Continuously rescaling a nearest-neighbor pixel
  image every frame would re-blur its edges on every single frame (scaling
  a crisp bitmap to a slightly different size doesn't stay crisp unless the
  scale factor is an exact integer ratio, which a smooth sine sweep never
  is) -- pulsing brightness instead keeps every rendered frame genuinely
  hard-edged while still reading as a twinkle, arguably even more so. This
  is a deliberate technique substitution, not a feature loss: the tier
  color, the crown at 30+, and the twinkle motion are all still there.
- **`_draw_zzz` was deliberately left as plain drawn text, not a pixel-grid
  glyph.** There's no small bitmap font anywhere in this codebase to draw
  "z" from a grid without inventing one from scratch -- well out of
  proportion to what three small drifting letters are worth this round.
  Antialiasing is turned off locally for just this call so it reads at
  least a little blockier than a fully smoothed font would, without
  pretending it's genuine pixel art. Recorded here rather than left
  unmentioned, per this project's own "flag it plainly" standard.
- **The speech-bubble card and its alarm-clock icon were not touched.**
  Per the spec's own scope ("the cat/mouse sprite art," not the surrounding
  UI chrome), and consistent with v1.14's own precedent of drawing the line
  between the character's own drawing code and the bubble/command-bar/
  Settings/Dashboard chrome that already went through `theme.py`. Confirmed
  via diff that `_draw_speech_bubble`, `nudge_bubble_size`, and
  `_draw_alarm_icon` are byte-for-byte the same logic as before (only their
  position in the file changed, not their content) -- only the small paw
  overlay drawn *alongside* the bubble (the nudge wave) changed this round,
  since that paw is part of the character, not the bubble card.

### Does this genuinely read as authentic pixel art? Yes -- a real technique change, not "smaller and blockier vector shapes"

Per the spec's own explicit aesthetic bar ("note plainly whether the
result genuinely achieves an authentic pixel-art feel or falls short of
it"): yes, and for reasons beyond a first glance --

- **Hard edges are structurally guaranteed**, not just visually likely --
  Part 0's deterministic pixel-exactness check proves nearest-neighbor
  scaling is actually in effect, not merely that the source art happens to
  look chunky.
- **Discrete animation is structurally guaranteed** too -- the
  `_image_cache`-size check proves exactly 2 frame grids exist for idle
  across 200 sampled timesteps, not a continuous interpolation that merely
  *looks* steppy at a glance.
- **A genuinely small, fixed palette per sprite** (4 colors for the cat,
  3 for the mouse, 2-3 per small-chrome icon), visibly flat-filled with no
  gradient or highlight anywhere -- confirmed by reading every literal grid
  string in `sprite.py` directly, not just eyeballing a render.
- Both the off-screen contact sheet (`verify_real_sheet.png`) and the live
  `KittenWindow` captures show every pose clearly distinct from its
  v1.15 predecessor: a blocky, staircase-edged silhouette instead of a
  smooth `QPainterPath` curve, visible individual "pixels" at the app's
  actual on-screen size, and eyes/mouths built from a handful of square
  cells instead of bezier arcs.

**One honest caveat**, in the same spirit as v1.13's list-scrollbar
disclosure and v1.15's sulk-stage-3-vs-purr similarity note, not smoothed
over: sulking stages 0 and 1 are visually very close to each other at the
app's actual small on-screen size (stage 1's "sliver" of revealed eye is a
single grid cell, faithfully matching how subtle the original vector
version's own stage-1 reveal was described as -- "a sliver" -- but a
single *pixel* reads as even more subtle than a single vector-curve sliver
did). Not treated as a defect to silently fix by exaggerating the reveal
beyond what the design calls for; recorded here instead, matching this
project's own standard for this kind of trade-off.

### `assets/demo.png` regenerated

Same 6-panel composition as before (Happy+Low Battery, 30-Day Streak,
Birthday, Purring, Sulking, Curious), same 600x480/200x240-per-panel
layout and label styling, rendered through the real `paint_kitten` off
-screen on the real `windows` platform plugin (same font-rendering
precaution as every prior demo.png regeneration). Compared side by side
against the pre-v1.16 image: every panel now shows a hard-edged, blocky
silhouette with a handful of flat square colors instead of a smooth
mascot-style outline -- genuinely, clearly a different rendering
*technique*, not a palette tweak. `README.md` already references this
exact filename with no hardcoded dimensions in its text, so no README
changes were needed.

### Testing

`pytest -q` -> unchanged at **234/234 passed** throughout -- this round is
pure drawing-code (`sprite.py`'s `QPainter`/pixel-grid rendering plus the
new `pixelart.py` engine), no pure-logic module touched, the same standard
`sprite.py` has always been held to (see section 12's Feature 3 for why
this file has never had a `test_sprite.py` of its own). Part 0's two
deterministic checks (pixel-exactness, hard-edge sweep) and the
`_image_cache`-size discreteness check above are the closest thing this
round has to unit tests for the new engine, run as scratch scripts
(scratchpad-only, not committed) rather than added to `tests/`, consistent
with `sprite.py`'s own long-standing exemption. `git status` was checked
before committing: only `src/gitten/sprite.py` (rewritten),
`src/gitten/pixelart.py` (new), and `assets/demo.png` (regenerated)
changed -- `window.py`, `mouse_window.py`, `main.py`,
`command_bar_window.py`, `settings_window.py`, and `dashboard_window.py`
were **not** touched, confirmed directly rather than assumed, since
`paint_kitten`/`paint_mouse`/`CANVAS`/`draw_particles`/`nudge_bubble_size`
(the only symbols anything outside `sprite.py` actually imports from it)
all kept their exact pre-v1.16 signatures.

### Files changed this round

`src/gitten/pixelart.py` (new), `src/gitten/sprite.py` (fully rewritten
internals, same public API), `assets/demo.png` (regenerated). No other
file in `src/gitten/` changed.
