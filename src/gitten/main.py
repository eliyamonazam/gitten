"""Entry point: builds the QApplication, system tray, window, and watcher."""

from __future__ import annotations

import asyncio
import sys
import time

from PySide6.QtCore import QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

import psutil

from gitten.attention import AttentionState, AttentionTracker, turn_stage
from gitten.distraction import (
    DEFAULT_CONFIG_PATH,
    DistractionTracker,
    is_distracting_window,
    load_distraction_lists,
)
from gitten.focus import DEFAULT_FOCUS_CONFIG_PATH, load_focus_substrings
from gitten.foreground_window import get_foreground_window
from gitten.git_watcher import GitWatcher, count_commits_today, get_commit_streak
from gitten.mood import Mood, MoodMachine
from gitten.notifications import fetch_notifications, request_access
from gitten.notifications import is_supported as notifications_supported
from gitten.oneliners import (
    pick_oneliner,
    random_interval_seconds,
    should_show_oneliner,
    should_show_rare_event,
)
from gitten.sprite import paint_kitten
from gitten.status_badge import StatusBadgeTracker
from gitten.system_monitor import is_focus_process_running, sample_system
from gitten.window import INBOX_ACCESS_NOT_GRANTED, INBOX_UNAVAILABLE, KittenWindow

ORG_NAME = "Gitten"
APP_NAME = "Gitten"
TICK_INTERVAL_MS = 5000
SYSTEM_SAMPLE_INTERVAL_MS = 7000
DISTRACTION_POLL_INTERVAL_MS = 3000
ATTENTION_TICK_INTERVAL_MS = 5000
FOCUS_POLL_INTERVAL_MS = 5000
NUDGE_MESSAGE = "یه وقفه کوتاه چطوره؟"


def _fetch_inbox_snapshot():
    """Blocking (one-shot asyncio.run) fetch of the current notification
    snapshot, run synchronously from the click handler that opens the inbox.

    A brief block on the UI thread is an acceptable v1.2 simplification --
    unlike the Telegram feature, nothing here needs a long-lived background
    event loop, just one WinRT round-trip triggered by a single click.
    """
    if not notifications_supported():
        return INBOX_UNAVAILABLE

    async def _run():
        if not await request_access():
            return None
        return await fetch_notifications()

    try:
        items = asyncio.run(_run())
    except Exception:
        return INBOX_UNAVAILABLE
    return INBOX_ACCESS_NOT_GRANTED if items is None else items


def _make_icon(mood: Mood, size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    paint_kitten(painter, QRectF(0, 0, size, size), mood, t=0.0)
    painter.end()
    return QIcon(pixmap)


class GittenApp:
    def __init__(self) -> None:
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.mood_machine = MoodMachine()
        self.badge_tracker = StatusBadgeTracker()
        self.distraction_tracker = DistractionTracker()
        self.attention_tracker = AttentionTracker()
        self.distracting_titles, self.distracting_processes = load_distraction_lists(
            DEFAULT_CONFIG_PATH
        )
        self.focus_substrings = load_focus_substrings(DEFAULT_FOCUS_CONFIG_PATH)
        self.watcher = GitWatcher()
        self.window = KittenWindow()
        self.window.set_context_menu_callback(self._show_context_menu)
        self.window.interacted.connect(self._on_interacted)
        self.window.plain_clicked.connect(self._on_plain_click)
        self._session_start = time.monotonic()

        self._build_tray()
        self._restore_position()
        self._restore_repo()

        self.watcher.commit_detected.connect(self._on_commit)
        self.watcher.dirty_changed.connect(self._on_dirty_changed)

        self._tick_timer = QTimer()
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start(TICK_INTERVAL_MS)

        self._system_timer = QTimer()
        self._system_timer.timeout.connect(self._on_system_tick)
        self._system_timer.start(SYSTEM_SAMPLE_INTERVAL_MS)

        self._distraction_timer = QTimer()
        self._distraction_timer.timeout.connect(self._on_distraction_tick)
        self._distraction_timer.start(DISTRACTION_POLL_INTERVAL_MS)

        self._attention_timer = QTimer()
        self._attention_timer.timeout.connect(self._on_attention_tick)
        self._attention_timer.start(ATTENTION_TICK_INTERVAL_MS)

        self._focus_timer = QTimer()
        self._focus_timer.timeout.connect(self._on_focus_tick)
        self._focus_timer.start(FOCUS_POLL_INTERVAL_MS)

        self._oneliner_timer = QTimer()
        self._oneliner_timer.setSingleShot(True)
        self._oneliner_timer.timeout.connect(self._on_oneliner_timer)
        self._schedule_next_oneliner()

        self.window.show()

    def _restore_position(self) -> None:
        pos = self.settings.value("window/pos")
        if pos is not None:
            self.window.move(pos)
        else:
            self.window.move(self.window.default_position())
        self.window.moved.connect(lambda p: self.settings.setValue("window/pos", p))

    def _restore_repo(self) -> None:
        repo = self.settings.value("repo/path")
        if repo and self.watcher.set_repo(repo):
            return
        self._prompt_choose_repo(required=False)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_icon(Mood.IDLE))
        self.tray.setToolTip("Gitten")

        menu = QMenu()
        self.repo_action = QAction("Choose watched repo...")
        self.repo_action.triggered.connect(lambda: self._prompt_choose_repo(required=False))
        menu.addAction(self.repo_action)

        menu.addSeparator()
        quit_action = QAction("Quit Gitten")
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.window.show()
            self.window.raise_()

    def _show_context_menu(self, global_pos) -> None:
        """The kitten's own right-click stats menu -- a quick glance, not a
        dashboard. Separate from (and in addition to) the tray icon's menu."""
        menu = QMenu()

        if self.watcher.repo_path is not None:
            commits = count_commits_today(self.watcher.repo_path)
            commits_text = (
                f"Commits today: {commits}" if commits is not None else "Commits today: --"
            )
            streak = get_commit_streak(self.watcher.repo_path)
            streak_text = f"Streak: {streak} day(s)" if streak is not None else "Streak: --"
            repo_text = f"Watching: {self.watcher.repo_path}"
        else:
            commits_text = "Commits today: --"
            streak_text = "Streak: --"
            repo_text = "Watching: (no repo chosen)"

        battery = psutil.sensors_battery()
        battery_text = f"Battery: {battery.percent:.0f}%" if battery else "Battery: n/a"
        uptime_text = f"Running for: {self._format_uptime()}"

        for text in (commits_text, streak_text, battery_text, repo_text, uptime_text):
            info_action = QAction(text)
            info_action.setEnabled(False)
            menu.addAction(info_action)

        menu.addSeparator()
        repo_action = QAction("Change watched repo...")
        repo_action.triggered.connect(lambda: self._prompt_choose_repo(required=False))
        menu.addAction(repo_action)

        quit_action = QAction("Quit Gitten")
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        menu.exec(global_pos)

    def _format_uptime(self) -> str:
        seconds = int(time.monotonic() - self._session_start)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

    def _prompt_choose_repo(self, required: bool) -> None:
        start_dir = str(self.watcher.repo_path) if self.watcher.repo_path else ""
        path = QFileDialog.getExistingDirectory(
            None, "Choose a git repository to watch", start_dir
        )
        if not path:
            if required:
                QMessageBox.warning(
                    None, "Gitten", "No repository chosen -- Gitten will stay idle."
                )
            return
        if self.watcher.set_repo(path):
            self.settings.setValue("repo/path", path)
            self.tray.setToolTip(f"Gitten -- watching {path}")
        else:
            QMessageBox.warning(
                None, "Gitten", f"'{path}' doesn't look like a git repository."
            )

    def _on_commit(self) -> None:
        mood = self.mood_machine.on_commit(now=time.monotonic())
        self._apply_mood(mood)
        self._apply_streak()

    def _on_dirty_changed(self, is_dirty: bool) -> None:
        mood = self.mood_machine.update_dirty(is_dirty, now=time.monotonic())
        self._apply_mood(mood)

    def _on_tick(self) -> None:
        mood = self.mood_machine.tick(now=time.monotonic())
        self._apply_mood(mood)
        self._apply_streak()

    def _apply_mood(self, mood: Mood) -> None:
        self.window.set_mood(mood)
        self.tray.setIcon(_make_icon(mood))

    def _apply_streak(self) -> None:
        streak = get_commit_streak(self.watcher.repo_path) if self.watcher.repo_path else 0
        self.window.set_streak(streak if streak is not None else 0)

    def _on_system_tick(self) -> None:
        sample = sample_system()
        badge = self.badge_tracker.update(
            battery_percent=sample.battery_percent,
            plugged_in=sample.plugged_in,
            cpu_percent=sample.cpu_percent,
            mem_percent=sample.mem_percent,
            disk_percent=sample.disk_percent,
        )
        self.window.set_badge(badge)

    def _on_interacted(self) -> None:
        self.attention_tracker.register_interaction(now=time.monotonic())

    def _on_plain_click(self) -> None:
        """A plain click while the "pet" view is showing. Per the v1.2
        interaction rule: while sulking, it's a pet (reconciliation
        progress); otherwise it opens the notification inbox."""
        now = time.monotonic()
        if self.attention_tracker.state == AttentionState.SULKING:
            self.attention_tracker.register_pet(now)
            self._apply_attention()
        else:
            self.window.open_inbox()
            self.window.set_inbox_items(_fetch_inbox_snapshot())

    def _apply_attention(self) -> None:
        if self.attention_tracker.state == AttentionState.SULKING:
            stage = turn_stage(self.attention_tracker.pets_received)
            self.window.set_attention(AttentionState.SULKING, stage)
        else:
            self.window.set_attention(AttentionState.NORMAL, None)

    def _on_attention_tick(self) -> None:
        self.attention_tracker.tick(now=time.monotonic())
        self._apply_attention()

    def _on_distraction_tick(self) -> None:
        fg = get_foreground_window()
        is_distracting = fg is not None and is_distracting_window(
            fg.process_name, fg.title, self.distracting_titles, self.distracting_processes
        )
        should_nudge = self.distraction_tracker.update(is_distracting, now=time.monotonic())
        if should_nudge:
            self.window.show_nudge(NUDGE_MESSAGE)

    def _on_focus_tick(self) -> None:
        self.window.set_focused(is_focus_process_running(self.focus_substrings))

    def _schedule_next_oneliner(self) -> None:
        self._oneliner_timer.start(int(random_interval_seconds() * 1000))

    def _on_oneliner_timer(self) -> None:
        """Fires on a random 45-90 minute cadence. Only actually shows the
        line if the cat is currently idle in its normal "pet" view -- not
        sulking, not in the notification inbox, not already showing another
        nudge. (There's no "mid-Telegram-alert" state to check yet, since
        the v1.3 Telegram reactions were never wired into main.py -- add
        that check here too once they are.) Otherwise this occurrence is
        silently skipped and the next one is rescheduled regardless."""
        is_sulking = self.attention_tracker.state == AttentionState.SULKING
        if should_show_oneliner(self.window.view_mode, is_sulking, self.window.is_nudging):
            if should_show_rare_event():
                self.window.trigger_shooting_star()
            else:
                self.window.show_nudge(pick_oneliner())
        self._schedule_next_oneliner()

    def run(self) -> int:
        return self.app.exec()


def main() -> int:
    gitten = GittenApp()
    return gitten.run()


if __name__ == "__main__":
    sys.exit(main())
