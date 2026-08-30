"""Watches a git repository's `.git` metadata and emits mood-relevant events.

Rather than shelling out to `git status` on a timer, this watches
`.git/COMMIT_EDITMSG` (touched on every commit) and `.git/index` (touched on
`git add` and other staging changes) with `watchdog`, the same pattern used
in the Wisp automation framework's `FileCreatedTrigger`. Only when one of
those files' mtimes change do we actually run `git status --porcelain`.
"""

from __future__ import annotations

import subprocess
import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from gitten.streak import compute_streak

# Debounce rapid-fire filesystem events (git can touch a file several times
# during a single operation) into a single status check.
_DEBOUNCE_SECONDS = 0.3


class _GitDirHandler(FileSystemEventHandler):
    def __init__(self, on_commit_msg_changed, on_index_changed):
        super().__init__()
        self._on_commit_msg_changed = on_commit_msg_changed
        self._on_index_changed = on_index_changed

    def _dispatch(self, path: str) -> None:
        name = Path(path).name
        if name == "COMMIT_EDITMSG":
            self._on_commit_msg_changed()
        elif name == "index":
            self._on_index_changed()

    def on_created(self, event):
        if not event.is_directory:
            self._dispatch(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._dispatch(event.src_path)


def _run_git_status(repo_path: Path) -> bool | None:
    """Return True if the repo has uncommitted changes, False if clean,
    None if the status check failed (e.g. not a git repo any more)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def count_commits_today(repo_path: Path) -> int | None:
    """Number of commits made since local midnight in ``repo_path``, or
    None if it can't be determined. Recomputed on demand rather than kept
    as a running counter, so it's always correct even after a restart."""
    try:
        result = subprocess.run(
            ["git", "log", "--since=midnight", "--oneline"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return len(lines)


def get_commit_streak(repo_path: Path) -> int | None:
    """Current consecutive-day commit streak in ``repo_path``, or None if it
    can't be determined. Recomputed from `git log` each time -- same idiom as
    `count_commits_today` -- rather than a running counter that could drift."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%ad", "--date=short"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    dates = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return compute_streak(dates, date.today())


class GitWatcher(QObject):
    """Emits Qt signals in response to git activity in a watched repo.

    commit_detected: a commit was just made.
    dirty_changed(bool): the working tree's dirty status, checked after any
        relevant `.git` file changes.
    """

    commit_detected = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._observer: Observer | None = None
        self._repo_path: Path | None = None
        self._last_check = 0.0

    @property
    def repo_path(self) -> Path | None:
        return self._repo_path

    def set_repo(self, repo_path: str | Path) -> bool:
        """Start watching a new repo path. Returns False if it isn't a git repo."""
        repo_path = Path(repo_path)
        git_dir = repo_path / ".git"
        if not git_dir.is_dir():
            return False

        self.stop()
        self._repo_path = repo_path

        handler = _GitDirHandler(
            on_commit_msg_changed=self._handle_commit,
            on_index_changed=self._handle_index_change,
        )
        self._observer = Observer()
        self._observer.schedule(handler, str(git_dir), recursive=False)
        self._observer.start()

        # Establish the initial dirty state right away.
        self._check_status()
        return True

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def _handle_commit(self) -> None:
        self.commit_detected.emit()
        self._check_status()

    def _handle_index_change(self) -> None:
        self._check_status_debounced()

    def _check_status_debounced(self) -> None:
        now = time.monotonic()
        if now - self._last_check < _DEBOUNCE_SECONDS:
            return
        self._last_check = now
        self._check_status()

    def _check_status(self) -> None:
        if self._repo_path is None:
            return
        is_dirty = _run_git_status(self._repo_path)
        if is_dirty is not None:
            self.dirty_changed.emit(is_dirty)
