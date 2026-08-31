# Gitten

A kitten that lives on your Windows desktop and taskbar: it watches a git
repo, reacts to your system and your habits, and has enough of its own
personality (moods, sulking, purring, random one-liners) that it reads as a
pet rather than a status bar widget.

![Gitten showing off a battery badge, a 30-day streak crown, a birthday hat, purring, sulking, and noticing a new app](assets/demo.png)

## Features

### Git awareness
- **Mood**: `idle` (closed eyes, "zzz") when there's been no git activity
  for a while, `happy` (heart + sparkles) right after a commit, `waiting`
  (worried eyes, a "!" bubble) once uncommitted changes have sat around too
  long (30+ minutes by default).
- **Daily commit streak**: a small star (3+ days), a twinkling gold star
  (7+), or a crown (30+) appears near its head, recomputed from the repo's
  full commit history rather than kept as a fragile running counter.

### System awareness
- A small badge near its head for critical/low battery, charging, high
  CPU/memory usage, or low disk space -- independent of mood, so it can be
  `happy` and show a badge at the same time.
- **Low-battery + uncommitted-changes combo**: no separate feature, just
  what naturally happens when both are true at once -- the `waiting`
  pose's "!" bubble becomes "‼" when a battery badge is also showing.

### Focus & productivity
- A gentle nudge (a paw-wave + speech bubble) if you've spent 20+ minutes
  straight on a distracting site or app.
- A "watching" reaction (perked ears, focused eyes) while a matching
  test/build process is running. Gitten only observes running processes,
  not their exit codes, so this can't tell you pass from fail -- just that
  something's running.

### Notifications
- Right-click-free access to your Windows notifications from a small inbox
  panel that slides open in place of the pet view. Needs a one-time
  Windows permission grant the first time you open it (Gitten will prompt);
  if it's denied or unsupported on your system, the inbox just says so
  instead of erroring.

### Personality & interaction
- **Sulking & reconciliation**: ignore Gitten for 30+ minutes and it turns
  away; a few pets bring it back around through visible in-between poses.
- **Hover purr**: hold the cursor over it for a moment (~0.2s) and it
  purrs -- distinct from any mood or focus pose, and it wins over both
  except while sulking.
- **High-five**: double-click for a quick raised-paw animation.
- **Draggable**, with a short sparkle trail that trails behind it in real
  screen space as you drag it around.
- **Random one-liners**: an occasional friendly Persian one-liner in a
  speech bubble every 45-90 minutes, skipped (not queued) if you're
  sulking, already seeing a nudge, or in the inbox view.
- **Shooting star**: a small chance (~5%) that a one-liner is replaced by
  a sparkle streaking across the window instead.

### Personalization
- **Rename** it and **set its birthday** from the tray menu (`QSettings`,
  so both persist across restarts).
- A small accessory renders above its head on Halloween (witch hat), Yalda
  (a pomegranate), and its own birthday (a party hat).
- Its body tint shifts slightly cooler/moonlit between 11pm and 7am --
  computed fresh on every repaint, no separate state to keep in sync.

**Everything above runs and stays entirely on your machine -- no network
calls, no telemetry**, with the sole exception of the in-progress Telegram
integration below, which is opt-in and not yet wired into the running app.

## How it's built

Rather than one large state machine, each of the areas above is its own
small, independent layer that gets composited together at paint time:
mood (`mood.py`, driven only by git activity), status badges
(`status_badge.py`, driven only by system readings), distraction/focus
(`distraction.py` / `focus.py`), attention/sulking (`attention.py`), and
seasonal/time-of-day rendering (`seasons.py`) all know nothing about each
other. That's deliberate, not incidental: it's what lets the cat be
`happy` from a commit, show a low-battery badge, and be mid-reconciliation
from a sulk, all at once, without any of those three systems needing to
special-case the others. Precedence between visually-competing overlays
(e.g. a hover purr vs. a focus reaction) is resolved once, explicitly, at
the point they'd otherwise collide, rather than baked into any one layer.

Most of these pure-logic layers have zero Qt imports and take their clock
(or RNG) as an argument rather than reading it internally, which is what
makes them fully unit-testable without a display or real elapsed time --
see `tests/`. The Qt-facing code (`window.py`, `sprite.py`, `main.py`)
stays comparatively thin wiring on top.

## Configuration

| What | Where |
|---|---|
| Watched git repo | Tray menu -> "Choose watched repo..." (also prompted on first run) -- persisted via `QSettings` |
| Cat's name | Tray menu -> "Rename..." -- persisted via `QSettings` |
| Cat's birthday | Tray menu -> "Set my birthday..." (`YYYY-MM-DD`) -- persisted via `QSettings` |
| Distracting titles/processes | `~/.gitten/distraction_config.json` (`{"titles": [...], "processes": [...]}`) -- falls back to a shipped default list (instagram/twitter/x.com/tiktok/reddit/youtube titles, telegram.exe/discord.exe processes) if missing |
| Test/build processes to react to | `~/.gitten/focus_config.json` (`{"substrings": [...]}`) -- falls back to a shipped default list (pytest, npm test, npm run build, cargo test, go test) if missing |
| Telegram credentials/session (see Roadmap) | `~/.gitten/telegram_config.json` + `~/.gitten/telegram.session*` -- never inside the project folder |
| Window position | Remembered automatically wherever you last dragged it (`QSettings`) |

`QSettings("Gitten", "Gitten")` lives at
`HKEY_CURRENT_USER\Software\Gitten\Gitten` on Windows. There's no in-app
settings UI beyond the tray prompts above -- editing the JSON files by hand
is the intended way to customize the distraction/focus lists for now.

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m gitten.main
```

On first run, Gitten asks which repository to watch. It sits near the
bottom-right of your primary screen, above the taskbar -- drag it anywhere,
and it remembers where you left it. Right-click it for a stats menu
(cat name, commits today, streak, battery, watched repo, session uptime),
or use the system tray icon for repo/rename/birthday/quit.

## Building the .exe

```bash
build_exe.bat
```

This produces a single portable `dist\Gitten.exe` via PyInstaller --
double-click to run, no install required. Must be run on Windows.

## Running tests

```bash
pip install -e .[dev]
pytest
```

Every pure-logic module (mood, status badges, distraction, focus,
attention, streak, particles, seasons, one-liners, notification
formatting, Telegram config paths) has its own test file under `tests/`.
The Qt-facing code (`window.py`, `sprite.py`, `main.py`) isn't covered by
pytest -- it's been verified end-to-end against real, live widget/app
instances during development (see `DEVELOPMENT_NOTES.md`), not just by
running the app manually.

## Project structure

```
gitten/
├── src/gitten/
│   ├── main.py               # entry point: QApplication, tray, window, watcher, all timers
│   ├── window.py              # transparent always-on-top draggable QWidget; view/click/drag/hover state
│   ├── sprite.py               # QPainter drawing code for every mood/pose/badge/accessory
│   ├── mood.py                  # pure git-mood state machine (idle/happy/waiting), no Qt imports
│   ├── git_watcher.py           # watchdog-based watcher; commit/streak/commits-today helpers
│   ├── status_badge.py          # pure state machine for battery/CPU/mem/disk badges
│   ├── distraction.py           # pure distraction-nudge streak logic + title/process list matching
│   ├── focus.py                  # pure test/build process-name matching + config loading
│   ├── system_monitor.py        # thin psutil wrapper (battery/CPU/mem/disk, running processes)
│   ├── foreground_window.py     # thin win32gui wrapper (active window/process)
│   ├── attention.py             # pure sulking/reconciliation state machine
│   ├── notifications.py         # thin WinRT wrapper + pure notification-text formatting
│   ├── streak.py                 # pure daily-commit-streak calculation from a set of dates
│   ├── particles.py              # pure fading-particle system (drag trail + shooting star)
│   ├── seasons.py                # pure seasonal-accessory + day/night-palette logic
│   ├── oneliners.py              # pure random one-liner/interval/rare-event selection
│   └── telegram_config.py       # pure Telegram credential/session path logic (no Telethon import)
├── scripts/
│   └── telegram_connection_test.py  # standalone Telegram login/listen script (see Roadmap)
├── tests/
│   └── test_*.py                # one file per pure module above
├── .github/workflows/ci.yml
├── pyproject.toml
├── build_exe.bat
└── LICENSE
```

## Roadmap

**Telegram integration is in progress, not unstarted.** A standalone
connection-test script (`scripts/telegram_connection_test.py`) and secure
credential/session handling (`telegram_config.py`, everything under
`~/.gitten/`, never inside the project folder) already exist and are
tested -- but the actual reactions (running over to the Telegram taskbar
icon, a "favorite contact" grab animation vs. a "bad contact" hiss +
warning badge, flashing the taskbar entry) are **not yet wired into the
main app**. The next step is building `telegram_watcher.py` and connecting
it in `main.py`; it's blocked on you supplying your own Telegram
`api_id`/`api_hash` (from Telegram's own site) to actually run the
standalone script end to end first.

Genuinely still deferred, not just unstarted busywork:
- Pass/fail-aware test/build reactions (would require Gitten to launch the
  command itself rather than only observe it running)
- A full settings UI (the distraction/focus lists are hand-edited JSON
  files, and cat name/birthday/repo are one-off tray prompts, by design
  for now)
- Live notification updates via WinRT's `NotificationChanged` event (the
  inbox currently does one fresh fetch each time it's opened)
- Reacting to GitHub Actions / CI status
- Decay during an interrupted reconciliation (petting partway through a
  sulk and never finishing currently just holds that stage indefinitely)
- Multiple kittens at once, unlockable skins/fur colors, sound effects,
  cross-platform support (Windows-only)

## License

MIT -- see [LICENSE](LICENSE).
