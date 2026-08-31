"""The dashboard (v1.12): a single at-a-glance, read-only status window --
unlike the settings panel, nothing here is editable. Reuses the exact same
"normal window" precedent `settings_window.py` established: a plain
`Qt.Window`, no transparency, no always-on-top, a real title bar. This and
the settings panel are the only two normal windows in the app; every other
window (`KittenWindow`, `MouseWindow`, `CommandBarWindow`) stays an overlay.

Every figure shown here is read from an existing data source rather than a
new one: `git_watcher.py`'s `get_commit_dates`/`get_commit_streak`/
`count_commits_this_week`, `streak.py`'s new `commits_by_day`/
`longest_streak` (both built from the same `get_commit_dates` data,
per the spec's explicit "don't add a second, differently-shaped git query"
instruction), `system_monitor.sample_system`, and the app's own live
tracker state (`mood_machine`, `attention_tracker`, `_is_away`,
`_format_uptime`). The Reminders section reuses `reminders.sorted_by_due`/
`format_reminder_row` -- the exact same two pieces the settings panel's
Reminders tab uses, pulled out into `reminders.py` alongside this file so
neither window duplicates the sort/formatting.

v1.13 styles this window from `theme.py`, purely visually -- every section
label is tagged `theme.mark_section_header`, and `_HeatmapWidget` now
paints its own rounded `theme.SURFACE_INSET` backdrop before drawing its
(unchanged) green-shaded cells, so it reads as sitting *in* the themed
window rather than pasted onto a mismatched background. The heatmap's own
data-encoding colors (`_HEATMAP_COLORS`/`_HEATMAP_EMPTY_COLOR`) are
deliberately untouched, per the spec.
"""

from __future__ import annotations

import time
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gitten import theme
from gitten.attention import AttentionState
from gitten.git_watcher import count_commits_this_week, get_commit_dates, get_commit_streak
from gitten.mood import Mood
from gitten.reminders import format_reminder_row, sorted_by_due
from gitten.streak import commits_by_day, longest_streak
from gitten.system_monitor import sample_system

_HEATMAP_WEEKS = 12
_CELL_SIZE = 12
_CELL_GAP = 3

# Light-to-dark shading by that day's commit count, in the same spirit as
# GitHub's own contribution graph -- deliberately fixed thresholds (not
# relative to the window's own max) so the same count always reads the same
# shade regardless of how busy the rest of the window was.
_HEATMAP_EMPTY_COLOR = QColor(230, 232, 235)
_HEATMAP_COLORS = [
    QColor(198, 228, 139),
    QColor(123, 201, 111),
    QColor(35, 154, 59),
    QColor(25, 99, 40),
]

_MOOD_LABELS = {
    Mood.IDLE: "idle",
    Mood.HAPPY: "happy",
    Mood.WAITING: "waiting for a commit",
}


def _shade_for_count(count: int) -> QColor:
    if count <= 0:
        return _HEATMAP_EMPTY_COLOR
    if count <= 1:
        return _HEATMAP_COLORS[0]
    if count <= 3:
        return _HEATMAP_COLORS[1]
    if count <= 6:
        return _HEATMAP_COLORS[2]
    return _HEATMAP_COLORS[3]


class _HeatmapWidget(QWidget):
    """A GitHub-contribution-style grid: one column per week (oldest to
    newest, left to right), one row per weekday (Monday..Sunday, top to
    bottom), each cell shaded by that day's commit count. Hand-drawn with
    `QPainter` primitives -- no external charting library -- the same
    "draw it yourself" approach every other visual in this app uses
    (`sprite.py`, the nudge bubble, the command bar backdrop)."""

    # Extra margin around the cell grid itself so the themed backdrop reads
    # as a real card with breathing room, not the grid's own tight _CELL_GAP
    # bleeding straight to the card's edge.
    _CARD_PADDING = 6

    def __init__(self) -> None:
        super().__init__()
        self._counts: dict[date, int] = {}
        width = _HEATMAP_WEEKS * (_CELL_SIZE + _CELL_GAP) + _CELL_GAP + self._CARD_PADDING * 2
        height = 7 * (_CELL_SIZE + _CELL_GAP) + _CELL_GAP + self._CARD_PADDING * 2
        self.setFixedSize(width, height)

    def set_counts(self, counts: dict[date, int]) -> None:
        self._counts = counts
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # v1.13: a themed card backdrop behind the (unchanged) data-colored
        # cells, so the heatmap sits *in* the window's surface rather than
        # floating on a mismatched default background -- see theme.py.
        painter.setPen(theme.BORDER)
        painter.setBrush(theme.SURFACE_INSET)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), theme.RADIUS, theme.RADIUS)

        painter.setPen(Qt.NoPen)
        if not self._counts:
            return
        oldest = min(self._counts)
        for day, count in self._counts.items():
            week_index = (day - oldest).days // 7
            row = day.weekday()  # 0=Monday .. 6=Sunday
            x = self._CARD_PADDING + _CELL_GAP + week_index * (_CELL_SIZE + _CELL_GAP)
            y = self._CARD_PADDING + _CELL_GAP + row * (_CELL_SIZE + _CELL_GAP)
            painter.setBrush(_shade_for_count(count))
            painter.drawRoundedRect(x, y, _CELL_SIZE, _CELL_SIZE, 2, 2)


class DashboardWindow(QDialog):
    def __init__(self, app) -> None:
        super().__init__(None)
        self._app = app
        self.setWindowTitle("Gitten Dashboard")
        self.setWindowFlags(Qt.Window)
        self.resize(420, 640)
        theme.apply_theme(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.SPACING_MD, theme.SPACING_MD, theme.SPACING_MD, theme.SPACING_MD)
        layout.setSpacing(theme.SPACING_SM)

        self._identity_label = QLabel()
        self._identity_label.setWordWrap(True)
        layout.addWidget(self._identity_label)

        layout.addSpacing(theme.SPACING_MD)
        layout.addWidget(self._header(f"Commit activity (last {_HEATMAP_WEEKS} weeks):"))
        self._heatmap = _HeatmapWidget()
        layout.addWidget(self._heatmap)

        streak_row = QHBoxLayout()
        streak_row.setSpacing(theme.SPACING_MD)
        self._current_streak_label = QLabel()
        self._best_streak_label = QLabel()
        streak_row.addWidget(self._current_streak_label)
        streak_row.addWidget(self._best_streak_label)
        streak_row.addStretch()
        layout.addLayout(streak_row)

        self._week_commits_label = self._muted("")
        layout.addWidget(self._week_commits_label)

        layout.addSpacing(theme.SPACING_MD)
        layout.addWidget(self._header("System:"))
        self._system_label = QLabel()
        layout.addWidget(self._system_label)

        layout.addSpacing(theme.SPACING_MD)
        layout.addWidget(self._header("Pending reminders:"))
        self._reminders_container = QWidget()
        self._reminders_layout = QVBoxLayout(self._reminders_container)
        self._reminders_layout.setContentsMargins(0, 0, 0, 0)
        self._reminders_layout.setSpacing(theme.SPACING_XS)
        layout.addWidget(self._reminders_container)

        layout.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        self.refresh()

    @staticmethod
    def _header(text: str) -> QLabel:
        label = QLabel(text)
        theme.mark_section_header(label)
        return label

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        theme.mark_muted_label(label)
        return label

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        """Recomputes and redraws every section from current live data.
        Called on open, on every system tick while this window is visible
        (see `GittenApp._on_system_tick`), and whenever the window is
        reopened."""
        self._refresh_identity()
        self._refresh_streak()
        self._refresh_system()
        self._refresh_reminders()

    def _refresh_identity(self) -> None:
        state = _MOOD_LABELS.get(self._app.mood_machine.mood, self._app.mood_machine.mood.value)
        if self._app.attention_tracker.state == AttentionState.SULKING:
            state = "sulking"
        if self._app._is_away:
            state = "away"
        self._identity_label.setText(
            f'<span style="color: {theme.ACCENT_PRESSED.name()}; font-size: 16px; '
            f'font-weight: 600;">{self._app.cat_name}</span><br>'
            f"{state} &middot; running for {self._app._format_uptime()}"
        )

    def _refresh_streak(self) -> None:
        repo_path = self._app.watcher.repo_path
        dates = get_commit_dates(repo_path) if repo_path is not None else None
        dates = dates or []

        self._heatmap.set_counts(commits_by_day(dates, weeks=_HEATMAP_WEEKS))

        current = get_commit_streak(repo_path) if repo_path is not None else None
        self._current_streak_label.setText(
            f"Current streak: <b>{current} day(s)</b>"
            if current is not None
            else "Current streak: --"
        )
        self._best_streak_label.setText(f"Best streak: <b>{longest_streak(dates)} day(s)</b>")

        week_commits = count_commits_this_week(repo_path) if repo_path is not None else None
        self._week_commits_label.setText(
            f"Commits this week: {week_commits}"
            if week_commits is not None
            else "Commits this week: --"
        )

    def _refresh_system(self) -> None:
        sample = sample_system()
        if sample.battery_percent is not None:
            battery_text = f"{sample.battery_percent:.0f}%"
            if sample.plugged_in:
                battery_text += " (charging)"
        else:
            battery_text = "n/a"
        self._system_label.setText(
            f"Battery: {battery_text}<br>"
            f"CPU: {sample.cpu_percent:.0f}%<br>"
            f"RAM: {sample.mem_percent:.0f}%<br>"
            f"Disk: {sample.disk_percent:.0f}%"
        )

    def _refresh_reminders(self) -> None:
        while self._reminders_layout.count():
            item = self._reminders_layout.takeAt(0)
            row_widget = item.widget()
            if row_widget is not None:
                row_widget.deleteLater()

        reminders = sorted_by_due(self._app.reminders)
        if not reminders:
            self._reminders_layout.addWidget(self._muted("No pending reminders."))
            return

        now = time.time()
        for reminder in reminders:
            self._reminders_layout.addWidget(QLabel(format_reminder_row(reminder, now)))
