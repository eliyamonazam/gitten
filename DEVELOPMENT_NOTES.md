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

## 13. Working agreement for this project

**Every change made to this codebase must be recorded in this file
(`DEVELOPMENT_NOTES.md`) in the same session it's made** — what was
built, why, and how it was tested — not just left implicit in the diff or
in a chat summary. This file is the durable record; treat updating it as
part of finishing the task, not an optional follow-up.
