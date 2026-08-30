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

## 9. v1.3 (in progress) — Telegram connection, step 1: standalone script

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

## 10. Working agreement for this project

**Every change made to this codebase must be recorded in this file
(`DEVELOPMENT_NOTES.md`) in the same session it's made** — what was
built, why, and how it was tested — not just left implicit in the diff or
in a chat summary. This file is the durable record; treat updating it as
part of finishing the task, not an optional follow-up.
