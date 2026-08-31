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

## 19. Working agreement for this project

**Every change made to this codebase must be recorded in this file
(`DEVELOPMENT_NOTES.md`) in the same session it's made** — what was
built, why, and how it was tested — not just left implicit in the diff or
in a chat summary. This file is the durable record; treat updating it as
part of finishing the task, not an optional follow-up.
