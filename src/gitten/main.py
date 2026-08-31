"""Entry point: builds the QApplication, system tray, window, and watcher."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import date

from PySide6.QtCore import QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

import psutil

from gitten.app_launch import DEFAULT_COOLDOWN_SECONDS, should_react_to_new_launch
from gitten.attention import AttentionState, AttentionTracker, turn_stage
from gitten.command_bar_hotkey import register_global_hotkey, unregister_global_hotkey
from gitten.command_bar_window import COMMAND_BAR_HEIGHT, COMMAND_BAR_WIDTH, CommandBarWindow
from gitten.commands import (
    COMMANDS_HELP_TEXT,
    UNKNOWN_COMMAND_REPLY,
    format_battery_reply,
    format_chase_reply,
    format_commits_reply,
    format_rename_reply,
    format_streak_reply,
    parse_command,
)
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
from gitten.mouse_game import (
    pick_spawn_position,
    random_spawn_interval_seconds,
    should_spawn_mouse,
)
from gitten.mouse_window import MouseWindow
from gitten.notifications import fetch_notifications, request_access
from gitten.notifications import is_supported as notifications_supported
from gitten.oneliners import (
    pick_oneliner,
    random_interval_seconds,
    should_show_oneliner,
    should_show_rare_event,
)
from gitten.reminders import (
    CANCEL_USAGE_REPLY,
    DEFAULT_REMINDERS_PATH,
    REMIND_USAGE_REPLY,
    Reminder,
    create_reminder,
    due_reminders,
    format_cancel_reply,
    format_cancel_unknown_reply,
    format_due_reply,
    format_flushed_reminders_reply,
    format_reminders_list,
    format_set_reply,
    load_reminders,
    next_reminder_id,
    parse_duration,
    save_reminders,
)
from gitten.seasons import seasonal_accessory
from gitten.sprite import paint_kitten
from gitten.status_badge import StatusBadgeTracker
from gitten.system_idle import get_idle_seconds, is_away
from gitten.system_monitor import is_focus_process_running, sample_system
from gitten.visible_windows import get_visible_window_pids
from gitten.window import (
    INBOX_ACCESS_NOT_GRANTED,
    INBOX_UNAVAILABLE,
    WINDOW_SIZE,
    KittenWindow,
    available_geometry,
)

ORG_NAME = "Gitten"
APP_NAME = "Gitten"
TICK_INTERVAL_MS = 5000
SYSTEM_SAMPLE_INTERVAL_MS = 7000
DISTRACTION_POLL_INTERVAL_MS = 3000
ATTENTION_TICK_INTERVAL_MS = 5000
FOCUS_POLL_INTERVAL_MS = 5000
NUDGE_MESSAGE = "یه وقفه کوتاه چطوره؟"
DEFAULT_CAT_NAME = "Gitten"

# v1.8: how long a real absence (system-wide keyboard/mouse idle, not the
# git-driven idle mood) has to have lasted, once the user comes back, before
# it's worth a small "welcome back" bubble -- deliberately a much longer bar
# than the away threshold itself (10 minutes) so a routine short break
# doesn't get greeted every time.
WELCOME_BACK_THRESHOLD_SECONDS = 1800.0  # 30 minutes
WELCOME_BACK_MESSAGE = "خوش برگشتی 🙂"


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
        self.cat_name = self.settings.value("cat/name", DEFAULT_CAT_NAME)
        stored_birthday = self.settings.value("cat/birthday")
        self.birthday = date.fromisoformat(stored_birthday) if stored_birthday else None
        self.mood_machine = MoodMachine()
        self.badge_tracker = StatusBadgeTracker()
        self.distraction_tracker = DistractionTracker()
        self.attention_tracker = AttentionTracker()
        self.distracting_titles, self.distracting_processes = load_distraction_lists(
            DEFAULT_CONFIG_PATH
        )
        self.focus_substrings = load_focus_substrings(DEFAULT_FOCUS_CONFIG_PATH)
        # v1.6 curiosity reaction: an empty baseline until the first system
        # tick actually polls -- should_react_to_new_launch treats an empty
        # previous-PID set as "establish the baseline, don't react", so the
        # very first poll never mistakes every already-running program for
        # a simultaneous new launch.
        self._known_window_pids: set[int] = set()
        self._last_curiosity_reaction_at: float | None = None
        # v1.7 mouse-chase minigame state: whether a chase is currently in
        # progress, and where the cat was standing right before it started
        # (so catching the mouse can walk it back there afterward without
        # permanently disturbing its saved/anchored position).
        self._is_chasing = False
        self._chase_start_pos = None
        # v1.8 real idle/away detection state: the current away flag (fed
        # into the three suppression gates below) and the monotonic
        # timestamp the current absence actually began -- computed as
        # "now minus however idle the very first away-poll already found
        # the system," not just the poll time, so the welcome-back check
        # measures the real absence length rather than undercounting it by
        # up to one system-tick interval.
        self._is_away = False
        self._away_since: float | None = None
        # v1.10 reminders: loaded once at startup, persisted to
        # ~/.gitten/reminders.json on every set/cancel/fire so they survive
        # a restart. Deliberately keyed to wall-clock time (time.time()),
        # not time.monotonic() like every other tracker's `now` above --
        # see reminders.py's module docstring for why.
        self.reminders = load_reminders(DEFAULT_REMINDERS_PATH)
        self.watcher = GitWatcher()
        self.window = KittenWindow()
        self.window.set_context_menu_callback(self._show_context_menu)
        self.window.interacted.connect(self._on_interacted)
        self.window.plain_clicked.connect(self._on_plain_click)
        self.window.walk_cancelled.connect(self._on_walk_cancelled)
        self.mouse_window = MouseWindow()
        self.command_bar = CommandBarWindow()
        self.command_bar.command_submitted.connect(self._on_command_submitted)
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

        self._mouse_spawn_timer = QTimer()
        self._mouse_spawn_timer.setSingleShot(True)
        self._mouse_spawn_timer.timeout.connect(self._on_mouse_spawn_timer)
        self._schedule_next_mouse_spawn()

        self._register_command_bar_hotkey()

        self.window.show()

    def _register_command_bar_hotkey(self) -> None:
        """v1.9 Part 4: Ctrl+Alt+G, system-wide, summons the command bar
        from anywhere. Bound to the kitten window's own HWND -- it already
        exists and doesn't need to be visible or focused for RegisterHotKey
        to work. Degrades gracefully (logged, no crash) if the combination
        is already claimed by something else -- see
        `command_bar_hotkey.register_global_hotkey`."""
        self._hotkey_filter = register_global_hotkey(
            int(self.window.winId()), self._show_command_bar
        )
        if self._hotkey_filter is not None:
            self.app.installNativeEventFilter(self._hotkey_filter)
        self.app.aboutToQuit.connect(self._unregister_command_bar_hotkey)

    def _unregister_command_bar_hotkey(self) -> None:
        if self._hotkey_filter is not None:
            unregister_global_hotkey(int(self.window.winId()))

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
        self._update_tray_tooltip()

        menu = QMenu()
        # Every QAction is parented to `menu` at construction, not just
        # added to it: QMenu.addAction(existing_action) does *not* reparent
        # or otherwise take ownership of a bare action the way Qt's C++ docs
        # might suggest -- an action with no Python reference kept anywhere
        # else is garbage-collected the instant its local variable goes out
        # of scope, silently vanishing from the menu before it's ever shown.
        # Confirmed concretely: without `parent=menu`, only `self.repo_action`
        # (kept alive as an instance attribute) and the separator (which
        # never gets a Python-side QAction wrapper at all) survived --
        # rename/birthday/quit were all gone from `menu.actions()`.
        self.repo_action = QAction("Choose watched repo...", menu)
        self.repo_action.triggered.connect(lambda: self._prompt_choose_repo(required=False))
        menu.addAction(self.repo_action)

        rename_action = QAction("Rename...", menu)
        rename_action.triggered.connect(self._prompt_rename)
        menu.addAction(rename_action)

        birthday_action = QAction("Set my birthday...", menu)
        birthday_action.triggered.connect(self._prompt_set_birthday)
        menu.addAction(birthday_action)

        menu.addSeparator()
        quit_action = QAction("Quit Gitten", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _update_tray_tooltip(self) -> None:
        if self.watcher.repo_path is not None:
            self.tray.setToolTip(f"{self.cat_name} -- watching {self.watcher.repo_path}")
        else:
            self.tray.setToolTip(self.cat_name)

    def _prompt_rename(self) -> None:
        name, ok = QInputDialog.getText(None, "Gitten", "Cat's name:", text=self.cat_name)
        if ok and name.strip():
            self._apply_rename(name.strip())

    def _apply_rename(self, name: str) -> None:
        """The actual rename effect, shared by the tray's "Rename..." dialog
        and v1.9's `rename <name>` command-bar command -- pulled out so
        neither one duplicates the settings-persist + tooltip-refresh
        logic."""
        self.cat_name = name
        self.settings.setValue("cat/name", self.cat_name)
        self._update_tray_tooltip()

    def _prompt_set_birthday(self) -> None:
        # QInputDialog has no date-entry convenience method in this Qt
        # binding (only text/int/double/item/multiline-text) -- confirmed by
        # checking dir(QInputDialog) rather than assuming, since the spec's
        # "a QInputDialog date entry is fine" turned out not to exist as
        # written. A validated YYYY-MM-DD text prompt is the equivalent.
        current = self.birthday.isoformat() if self.birthday else ""
        text, ok = QInputDialog.getText(
            None, "Gitten", "Cat's birthday (YYYY-MM-DD):", text=current
        )
        if not ok or not text.strip():
            return
        try:
            parsed = date.fromisoformat(text.strip())
        except ValueError:
            QMessageBox.warning(None, "Gitten", f"'{text}' isn't a valid date (use YYYY-MM-DD).")
            return
        self.birthday = parsed
        self.settings.setValue("cat/birthday", self.birthday.isoformat())

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.window.show()
            self.window.raise_()

    def _show_context_menu(self, global_pos) -> None:
        """The kitten's own right-click stats menu -- a quick glance, not a
        dashboard. Separate from (and in addition to) the tray icon's menu."""
        menu = QMenu()

        # Every QAction below is parented to `menu` -- see the comment in
        # `_build_tray` for why: without it, each of these (being plain
        # local variables, the loop variable especially) is garbage
        # collected before `menu.exec()` even runs, silently stripping the
        # menu down to almost nothing right before it's shown.
        for text in self._stats_menu_lines():
            info_action = QAction(text, menu)
            info_action.setEnabled(False)
            menu.addAction(info_action)

        menu.addSeparator()
        repo_action = QAction("Change watched repo...", menu)
        repo_action.triggered.connect(lambda: self._prompt_choose_repo(required=False))
        menu.addAction(repo_action)

        quit_action = QAction("Quit Gitten", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        menu.exec(global_pos)

    def _stats_menu_lines(self) -> list[str]:
        """The disabled info lines shown at the top of the right-click stats
        menu, in order: a "-- {name} --" header, then commits/streak/
        battery/repo/uptime. Pulled out of `_show_context_menu` so it can be
        exercised directly without going through a real, blocking
        `QMenu.exec()` popup -- that's not something this project's headless
        test tooling can drive safely (see the v1.5 Feature 6 dev notes)."""
        lines = [f"-- {self.cat_name} --"]

        if self.watcher.repo_path is not None:
            commits = count_commits_today(self.watcher.repo_path)
            lines.append(
                f"Commits today: {commits}" if commits is not None else "Commits today: --"
            )
            streak = get_commit_streak(self.watcher.repo_path)
            lines.append(f"Streak: {streak} day(s)" if streak is not None else "Streak: --")
            repo_text = f"Watching: {self.watcher.repo_path}"
        else:
            lines.append("Commits today: --")
            lines.append("Streak: --")
            repo_text = "Watching: (no repo chosen)"

        battery = psutil.sensors_battery()
        lines.append(f"Battery: {battery.percent:.0f}%" if battery else "Battery: n/a")
        lines.append(repo_text)
        lines.append(f"Running for: {self._format_uptime()}")
        return lines

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
            self._update_tray_tooltip()
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
        self._apply_accessory()

    def _apply_accessory(self) -> None:
        self.window.set_accessory(seasonal_accessory(date.today(), self.birthday))

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
        self._check_idle()
        self._check_app_launch()
        self._check_reminders()

    def _check_idle(self) -> None:
        """v1.8: real system-wide keyboard/mouse idle detection, piggybacked
        on the existing ~7s system-status timer rather than a new one, per
        the spec. Drives both the AWAY sleep pose (via `window.set_away`)
        and, on the away->active transition after a long-enough absence, the
        welcome-back nudge. v1.10 also flushes any reminders that came due
        during the absence at this exact same transition point -- see
        `_flush_due_reminders`."""
        idle_seconds = get_idle_seconds()
        now = time.monotonic()
        away_now = is_away(idle_seconds)

        if away_now and not self._is_away:
            # Just went away -- the absence actually started `idle_seconds`
            # ago, not just now, so anchor `_away_since` to that real start
            # time rather than the poll time.
            self._away_since = now - idle_seconds
        elif not away_now and self._is_away and self._away_since is not None:
            absence = now - self._away_since
            flushed_reminders = self._flush_due_reminders()
            # A flushed reminder is more meaningful, user-requested content
            # than the ambient welcome-back line -- only show the generic
            # message when there was nothing to flush, rather than racing
            # two nudges into the single bubble slot.
            if (
                not flushed_reminders
                and absence >= WELCOME_BACK_THRESHOLD_SECONDS
                and self.window.view_mode == "pet"
            ):
                self.window.show_nudge(WELCOME_BACK_MESSAGE)
            self._away_since = None

        self._is_away = away_now
        self.window.set_away(away_now)

    def _check_reminders(self) -> None:
        """v1.10: checked on the same ~7s system-status tick as the badge/
        idle/curiosity checks above, per the spec -- no new timer. Deliberately
        does **not** apply `is_away` suppression the way `_check_app_launch`/
        `_on_oneliner_timer`/`_on_mouse_spawn_timer` do for v1.8's ambient
        personality touches: a reminder is something the user explicitly
        asked for at a specific time, so while AWAY this just holds off
        (leaving it in `self.reminders`, still due on every check) rather
        than firing it into an empty room -- `_flush_due_reminders` (called
        from `_check_idle`'s away->active transition) is what actually shows
        it once someone's there to see it."""
        if self._is_away:
            return
        due = due_reminders(self.reminders, time.time())
        if due:
            self._fire_reminders(due)

    def _flush_due_reminders(self) -> bool:
        """Fires any reminders that became due during an absence, reusing
        the exact away->active transition point `_check_idle` already has
        for the v1.8 welcome-back message, per the spec's explicit
        instruction not to add a second hook for "the user just came back."
        Returns True if anything was flushed, so `_check_idle` can skip the
        generic welcome-back nudge in favor of this more specific one."""
        due = due_reminders(self.reminders, time.time())
        if not due:
            return False
        self._fire_reminders(due)
        return True

    def _fire_reminders(self, due: list[Reminder]) -> None:
        """Shared by both firing paths above: removes the given (already-due)
        reminders from the pending list, persists the change, and shows a
        single reply through the existing nudge bubble -- the plain "due"
        reply for one, or a combined listing if several came due at once
        (e.g. several piling up during one absence)."""
        due_ids = {r.id for r in due}
        self.reminders = [r for r in self.reminders if r.id not in due_ids]
        save_reminders(self.reminders, DEFAULT_REMINDERS_PATH)
        if len(due) == 1:
            self.window.show_nudge(format_due_reply(due[0]))
        else:
            self.window.show_nudge(format_flushed_reminders_reply(due))

    def _check_app_launch(self) -> None:
        """v1.6: piggybacks on the existing ~7s system-status timer rather
        than adding a new one, per the spec."""
        now = time.monotonic()
        current_pids = get_visible_window_pids()
        if should_react_to_new_launch(
            self._known_window_pids,
            current_pids,
            self._last_curiosity_reaction_at,
            now,
            cooldown=DEFAULT_COOLDOWN_SECONDS,
            is_away=self._is_away,
        ):
            self._last_curiosity_reaction_at = now
            self.window.trigger_curiosity()
        self._known_window_pids = current_pids

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
        if should_show_oneliner(
            self.window.view_mode, is_sulking, self.window.is_nudging, is_away=self._is_away
        ):
            if should_show_rare_event():
                self.window.trigger_shooting_star()
            else:
                self.window.show_nudge(pick_oneliner())
        self._schedule_next_oneliner()

    def _schedule_next_mouse_spawn(self) -> None:
        self._mouse_spawn_timer.start(int(random_spawn_interval_seconds() * 1000))

    def _on_mouse_spawn_timer(self) -> None:
        """Fires on its own random 45-90 minute cadence (v1.7), independent
        of the one-liner timer. Only actually starts a chase if
        should_spawn_mouse's gating passes -- otherwise this occurrence is
        silently skipped and the next one is rescheduled regardless, same
        "always reschedule" pattern as _on_oneliner_timer."""
        is_sulking = self.attention_tracker.state == AttentionState.SULKING
        if should_spawn_mouse(
            self.window.view_mode,
            is_sulking,
            self._is_chasing,
            self.window.is_dragging,
            is_away=self._is_away,
        ):
            self._start_mouse_chase()
        self._schedule_next_mouse_spawn()

    def _start_mouse_chase(self) -> None:
        geo = available_geometry()
        cat_pos = self.window.pos()
        mouse_x, mouse_y = pick_spawn_position(
            geo.left(), geo.top(), geo.right(), geo.bottom(), cat_pos.x(), cat_pos.y()
        )
        self._chase_start_pos = cat_pos
        self._is_chasing = True
        self.mouse_window.show_at(mouse_x, mouse_y)
        self.window.walk_to(int(mouse_x), int(mouse_y), on_arrived=self._on_mouse_caught)

    def _on_mouse_caught(self) -> None:
        """The cat's walk_to toward the mouse arrived -- "caught" it. Hides
        the mouse, plays a catch-effect particle burst at the cat's current
        position, then walks the cat back to wherever it was standing
        before the chase started so the game doesn't permanently disturb
        its saved/anchored position."""
        self.mouse_window.hide()
        self.window.trigger_catch_effect()
        self._is_chasing = False
        return_pos = self._chase_start_pos
        self._chase_start_pos = None
        if return_pos is not None:
            self.window.walk_to(return_pos.x(), return_pos.y())

    def _on_walk_cancelled(self) -> None:
        """A real user drag interrupted an in-progress walk_to (Part 1's
        rule: user input always wins over an autonomous animation). If this
        happened mid-chase, don't leave the mouse window stranded on screen
        with nothing chasing it -- hide it and reset the chase state right
        away. (If it happened during the *return* walk after already
        catching the mouse, _is_chasing is already False by then and this
        is correctly a no-op -- there's no mouse window left to hide.)"""
        if self._is_chasing:
            self.mouse_window.hide()
            self._is_chasing = False
            self._chase_start_pos = None

    # -- v1.9: quick command bar ------------------------------------------

    def _show_command_bar(self) -> None:
        """Summoned by the global hotkey (registered in `run()`) -- shows
        the command bar just above the cat's current position, clamped to
        stay fully on the primary screen's available geometry the same way
        v1.7's mouse-spawn point picking already clamps to it."""
        cat_pos = self.window.pos()
        geo = available_geometry()
        x = cat_pos.x() + (WINDOW_SIZE - COMMAND_BAR_WIDTH) // 2
        y = cat_pos.y() - COMMAND_BAR_HEIGHT - 8
        x = max(geo.left(), min(x, geo.right() - COMMAND_BAR_WIDTH))
        y = max(geo.top(), y)
        self.command_bar.show_near(x, y)

    def _on_command_submitted(self, text: str) -> None:
        """The command-bar popup emits the raw typed text on Enter -- this
        parses it and runs the matching handler, then (for every command but
        `quit`) shows the reply through the existing nudge/one-liner bubble
        mechanism, reusing it exactly the way v1.8's welcome-back message
        did rather than adding any new response-rendering."""
        command, argument = parse_command(text)
        reply = self._dispatch_command(command, argument)
        if reply is not None:
            self.window.show_nudge(reply)

    def _dispatch_command(self, command: str, argument: str) -> str | None:
        """Runs one command-bar command and returns the reply text to show,
        or None only for `quit` (which just exits instead of replying).
        Each handler reuses the existing mechanism it corresponds to --
        streak/commits reuse `git_watcher.py`, rename reuses `_apply_rename`
        (shared with the tray dialog), chase reuses the v1.7 mouse-chase
        machinery -- rather than duplicating any of that logic here."""
        if command == "streak":
            streak = (
                get_commit_streak(self.watcher.repo_path) if self.watcher.repo_path else None
            )
            return format_streak_reply(streak)
        if command == "commits":
            commits = (
                count_commits_today(self.watcher.repo_path) if self.watcher.repo_path else None
            )
            return format_commits_reply(commits)
        if command == "battery":
            battery = psutil.sensors_battery()
            return format_battery_reply(battery.percent if battery else None)
        if command == "rename":
            if argument:
                self._apply_rename(argument)
            return format_rename_reply(argument)
        if command == "chase":
            already_chasing = self._is_chasing
            if not already_chasing:
                self._start_mouse_chase()
            return format_chase_reply(already_chasing=already_chasing)
        if command == "remind":
            return self._handle_remind_command(argument)
        if command == "reminders":
            return format_reminders_list(self.reminders, time.time())
        if command == "cancel":
            return self._handle_cancel_command(argument)
        if command == "help":
            return COMMANDS_HELP_TEXT
        if command == "quit":
            self.app.quit()
            return None
        return UNKNOWN_COMMAND_REPLY

    def _handle_remind_command(self, argument: str) -> str:
        """`remind <duration> <message>` -- parses the duration off the
        front of `argument` via `reminders.parse_duration` (the same "pure
        parsing returns a tuple" convention `commands.parse_command` already
        established), and replies with the usage hint for either malformed
        case (no valid duration token, or a duration with nothing after
        it) rather than silently doing nothing, per the spec."""
        seconds, message = parse_duration(argument)
        message = message.strip()
        if seconds is None or not message:
            return REMIND_USAGE_REPLY
        reminder = create_reminder(
            next_reminder_id(self.reminders), message, seconds, time.time()
        )
        self.reminders.append(reminder)
        save_reminders(self.reminders, DEFAULT_REMINDERS_PATH)
        return format_set_reply(reminder.message, seconds)

    def _handle_cancel_command(self, argument: str) -> str:
        """`cancel <id>` -- the id shown by the `reminders` command."""
        id_text = argument.strip()
        if not id_text:
            return CANCEL_USAGE_REPLY
        try:
            target_id = int(id_text)
        except ValueError:
            return format_cancel_unknown_reply(id_text)
        match = next((r for r in self.reminders if r.id == target_id), None)
        if match is None:
            return format_cancel_unknown_reply(id_text)
        self.reminders = [r for r in self.reminders if r.id != target_id]
        save_reminders(self.reminders, DEFAULT_REMINDERS_PATH)
        return format_cancel_reply(match)

    def run(self) -> int:
        return self.app.exec()


def main() -> int:
    gitten = GittenApp()
    return gitten.run()


if __name__ == "__main__":
    sys.exit(main())
