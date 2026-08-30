# Gitten — a git-aware desktop kitten for Windows

## One-line pitch
A cute pixel-style kitten that lives on the Windows taskbar and reacts to git activity in a watched repository: it sleeps when idle, celebrates after a commit, and looks worried when uncommitted changes pile up.

## Why this project
- Desktop-pet apps are a proven, well-loved GitHub genre (see: Desktop Goose, Bongo Cat, Shimeji ports) — visually charming, low barrier to trying it, high star potential.
- The git-reactive twist targets the exact audience that browses GitHub (developers), making it more relatable than a generic pet.
- Reuses skills already built in a previous project ("Wisp", a Python automation framework): `watchdog` for file/repo watching, clean package structure, pytest, GitHub Actions CI, PyInstaller-style packaging mindset.
- New skill being added: a real desktop GUI app (transparent always-on-top window, system tray, sprite rendering) — this is the part that needs Windows to build and verify properly.

## Core mechanic
The app watches one local git repository (path configurable) and drives a simple mood state machine:

| State | Trigger | Visual |
|---|---|---|
| `idle/sleep` | No git activity for a while | Eyes closed, "zzz" above head |
| `happy` | A `git commit` was just made in the watched repo | Eyes closed happily (^ ^), small heart/sparkle above head, brief animation |
| `waiting` | Uncommitted changes have been sitting for too long (configurable threshold, e.g. 30+ minutes) | Wide worried eyes, raised eyebrows, small "!" bubble above head |

Detecting git activity: no need to shell out to `git` on a timer. Watch `.git/COMMIT_EDITMSG` (updates on every commit) and `.git/index` (updates on `git add`) with `watchdog`, same pattern used in Wisp's `FileCreatedTrigger`. Use `git status --porcelain` (via `subprocess`) only when the mtime changes, not on a tight loop.

## MVP scope (v1 — build this first, keep it small)
- [ ] Frameless, transparent, always-on-top window using PySide6 (`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`, `Qt.WA_TranslucentBackground`)
- [ ] Kitten rendered with `QPainter` (simple shapes — ellipse body, triangle ears, path-based tail — no external art assets needed; see "Visual reference" below for exact shapes/colors already designed)
- [ ] Three mood states wired to real git events as described above
- [ ] Sits anchored near the bottom of the primary screen (approximates "sitting on the taskbar"); draggable with the mouse
- [ ] System tray icon (`QSystemTrayIcon`) with: choose watched repo folder, quit
- [ ] Packaged as a single portable `Gitten.exe` via PyInstaller (`--onefile --windowed --noconsole`), double-click to run, no install/setup required
- [ ] Unit tests for the state-machine logic (mood transitions), following the same pytest style as Wisp — GUI rendering itself doesn't need unit tests, but the "what mood should we be in given these git signals" logic does
- [ ] README with a GIF/screenshot, MIT license, clean repo structure

## Explicitly out of scope for v1 (future roadmap, note in README, don't build now)
- Multiple kittens at once
- Reacting to GitHub Actions / CI status (would need a GitHub token + API polling)
- Unlockable skins/fur colors
- Sound effects
- Cross-platform support (Windows-only for v1; the transparency/always-on-top approach is more reliable to get right on one platform first)

## Tech stack
- **Python 3.11+**
- **PySide6** (Qt) — chosen over Pygame/tkinter because it has native, reliable cross-DPI transparency and system tray support, avoiding fragile `ctypes`/`win32` transparency hacks
- **watchdog** — already used in Wisp, same mental model
- **pytest** — for the state machine logic
- **PyInstaller** — for the final `.exe` (must be run on Windows to produce a Windows executable)
- **GitHub Actions** — CI that at minimum runs the unit tests on `windows-latest`

## Suggested project structure
```
gitten/
├── src/gitten/
│   ├── __init__.py
│   ├── main.py            # entry point, builds the QApplication + tray + window
│   ├── window.py           # the transparent always-on-top QWidget
│   ├── sprite.py           # QPainter drawing code for the kitten (idle/happy/waiting)
│   ├── mood.py             # pure logic: state machine, no Qt imports (easy to unit test)
│   └── git_watcher.py       # watchdog-based watcher emitting mood-relevant events
├── tests/
│   └── test_mood.py
├── .github/workflows/ci.yml
├── pyproject.toml
├── build_exe.bat            # thin wrapper around the PyInstaller command
├── README.md
└── LICENSE
```

## Visual reference (already designed — replicate these shapes/colors)
Body color: `#E8935F` (coral/orange), inner ear color: `#F5B98A`, outline/features: `#2C2C2A`.

- **Idle/sleep**: two short horizontal closed-eye lines, small `~` mouth, italic gray "zzz" text above the head.
- **Happy**: two small upward curves for closed happy eyes, open smiling curve mouth, a small heart shape above the head.
- **Waiting**: two white circles with small black pupils (wide eyes), short angled eyebrow lines above each eye, small wavy concerned mouth, a small circular speech bubble with "!" above the head.

Base shape: an ellipse body/head combined (chibi-style blob, no separate neck), two triangle ears with a smaller lighter-color inner triangle, a curved tail as a thick rounded stroke path.

## How to start in Claude Code
1. Create an empty folder (e.g. `gitten/`) and open it in Claude Code.
2. Put this file in the folder as `GITTEN_SPEC.md`.
3. Prompt: "Read GITTEN_SPEC.md and build the v1 MVP described in it. Follow the suggested project structure. Ask me before adding any dependency not listed in the tech stack."
4. Iterate visually — run it, take a look at the actual kitten on your desktop, and give feedback the way you would to me (e.g. "the ears look too big", "make it react faster after a commit").
