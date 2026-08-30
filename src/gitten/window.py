"""The transparent, always-on-top, frameless kitten widget."""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gitten.attention import AttentionState
from gitten.mood import Mood
from gitten.notifications import NotificationItem
from gitten.sprite import paint_kitten
from gitten.status_badge import Badge

WINDOW_SIZE = 130
INBOX_SIZE = QSize(240, 300)
ANIMATION_INTERVAL_MS = 33  # ~30 fps
TASKBAR_MARGIN = 4
_DRAG_THRESHOLD = 4
NUDGE_DURATION_SECONDS = 4.0
_NUDGE_FADE_SECONDS = 1.0

# Shown in the inbox view for the two distinct "nothing to show" causes the
# v1.2 spec calls out -- kept as plain strings (not exceptions) so
# `set_inbox_items` can't be misused to smuggle a real error through.
INBOX_UNAVAILABLE = "unavailable"
INBOX_ACCESS_NOT_GRANTED = "not_granted"


class KittenWindow(QWidget):
    moved = Signal(QPoint)
    # Any left- or right-button press on the cat, whether or not it turns
    # into a drag -- resets the v1.2 sulk clock regardless of what else
    # happens with the click.
    interacted = Signal()
    # A plain click-and-release in place, while in the "pet" view. main.py
    # decides whether that means "open the inbox" or "count as a pet",
    # based on the current attention state -- this widget doesn't need to
    # know which.
    plain_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.resize(WINDOW_SIZE, WINDOW_SIZE)

        self._mood = Mood.IDLE
        self._badge = Badge.NONE
        self._streak = 0
        self._focused = False
        self._nudge_text: str | None = None
        self._nudge_started_at: float | None = None
        self._start_time = time.monotonic()
        self._dragging = False
        self._drag_moved = False
        self._drag_offset = QPoint()

        self._view_mode = "pet"  # or "inbox"
        self._attention_state = AttentionState.NORMAL
        self._turn_stage: int | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(ANIMATION_INTERVAL_MS)

        self._context_menu_requested_callback = None

        self._build_inbox_panel()

    def _build_inbox_panel(self) -> None:
        """The notification-inbox view: a plain opaque panel with a back
        arrow and a scrollable list, laid out as a child widget so it lives
        inside this same frameless/topmost/draggable window rather than a
        second one (per the v1.2 spec)."""
        self._inbox_panel = QWidget(self)
        self._inbox_panel.setStyleSheet(
            "background-color: rgba(32, 32, 36, 235); border-radius: 10px;"
        )

        self._back_button = QToolButton(self._inbox_panel)
        self._back_button.setText("←")
        self._back_button.setStyleSheet(
            "color: white; font-size: 16px; border: none; background: transparent;"
        )
        self._back_button.setCursor(Qt.PointingHandCursor)
        self._back_button.clicked.connect(self.close_inbox)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._back_button)
        header.addStretch()

        self._notification_list = QListWidget(self._inbox_panel)
        self._notification_list.setStyleSheet(
            "QListWidget { background: transparent; color: white; border: none; }"
            "QListWidget::item { padding: 4px 2px; }"
        )
        self._notification_list.setWordWrap(True)

        self._empty_label = QLabel(self._inbox_panel)
        self._empty_label.setStyleSheet("color: #cccccc;")
        self._empty_label.setWordWrap(True)
        self._empty_label.hide()

        layout = QVBoxLayout(self._inbox_panel)
        layout.addLayout(header)
        layout.addWidget(self._notification_list)
        layout.addWidget(self._empty_label)

        self._inbox_panel.hide()

    def default_position(self) -> QPoint:
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        if geo is None:
            return QPoint(100, 100)
        x = geo.right() - WINDOW_SIZE - 60
        y = geo.bottom() - WINDOW_SIZE + TASKBAR_MARGIN
        return QPoint(max(geo.left(), x), y)

    def set_mood(self, mood: Mood) -> None:
        if mood != self._mood:
            self._mood = mood
            self.update()

    def set_badge(self, badge: Badge) -> None:
        if badge != self._badge:
            self._badge = badge
            self.update()

    def set_streak(self, streak: int) -> None:
        if streak != self._streak:
            self._streak = streak
            self.update()

    def set_focused(self, focused: bool) -> None:
        if focused != self._focused:
            self._focused = focused
            self.update()

    def show_nudge(self, text: str) -> None:
        self._nudge_text = text
        self._nudge_started_at = time.monotonic()

    @property
    def is_nudging(self) -> bool:
        return self._nudge_text is not None

    def set_context_menu_callback(self, callback) -> None:
        self._context_menu_requested_callback = callback

    def set_attention(self, state: AttentionState, turn_stage: int | None) -> None:
        """`turn_stage` is 0-3 while SULKING; pass None once reconciled/NORMAL
        so the normal front-facing mood rendering resumes unchanged."""
        if state != self._attention_state or turn_stage != self._turn_stage:
            self._attention_state = state
            self._turn_stage = turn_stage
            self.update()

    @property
    def view_mode(self) -> str:
        return self._view_mode

    def open_inbox(self) -> None:
        if self._view_mode == "inbox":
            return
        self._view_mode = "inbox"
        self._resize_anchored_bottom_right(INBOX_SIZE)
        self._inbox_panel.setGeometry(0, 0, self.width(), self.height())
        self._inbox_panel.show()
        self.update()

    def close_inbox(self) -> None:
        if self._view_mode != "inbox":
            return
        self._view_mode = "pet"
        self._inbox_panel.hide()
        self._resize_anchored_bottom_right(QSize(WINDOW_SIZE, WINDOW_SIZE))
        self.update()

    def set_inbox_items(self, items: str | list[NotificationItem]) -> None:
        """`items` is INBOX_UNAVAILABLE, INBOX_ACCESS_NOT_GRANTED, or a
        (possibly empty) list of `NotificationItem`."""
        self._notification_list.clear()

        if items == INBOX_UNAVAILABLE:
            self._show_inbox_message("Notifications unavailable.")
            return
        if items == INBOX_ACCESS_NOT_GRANTED:
            self._show_inbox_message(
                "Notification access not granted yet.\n"
                "Allow it in Windows Settings -> Privacy -> Notifications, "
                "then click the cat again."
            )
            return
        if not items:
            self._show_inbox_message("No notifications right now.")
            return

        self._empty_label.hide()
        self._notification_list.show()
        for item in items:
            text = f"{item.app_name}  ·  {item.time_text}\n{item.text}"
            self._notification_list.addItem(QListWidgetItem(text))

    def _show_inbox_message(self, text: str) -> None:
        self._notification_list.hide()
        self._empty_label.setText(text)
        self._empty_label.show()

    def _resize_anchored_bottom_right(self, new_size: QSize) -> None:
        """Grow/shrink the window while keeping its bottom-right corner
        fixed -- it sits near the taskbar, so anchoring there (rather than
        the top-left) keeps the inbox from growing off-screen."""
        bottom_right = self.geometry().bottomRight()
        rect = QRect(0, 0, new_size.width(), new_size.height())
        rect.moveBottomRight(bottom_right)
        self.setGeometry(rect)

    def _nudge_opacity(self, now: float) -> float:
        if self._nudge_text is None or self._nudge_started_at is None:
            return 0.0
        elapsed = now - self._nudge_started_at
        if elapsed >= NUDGE_DURATION_SECONDS:
            self._nudge_text = None
            self._nudge_started_at = None
            return 0.0
        remaining = NUDGE_DURATION_SECONDS - elapsed
        if remaining >= _NUDGE_FADE_SECONDS:
            return 1.0
        return remaining / _NUDGE_FADE_SECONDS

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._view_mode == "inbox":
            return  # the inbox panel (child widgets) paints itself
        painter = QPainter(self)
        rect = QRectF(0, 0, self.width(), self.height())
        now = time.monotonic()
        elapsed = now - self._start_time
        nudge_opacity = self._nudge_opacity(now)
        paint_kitten(
            painter,
            rect,
            self._mood,
            elapsed,
            dragging=self._dragging,
            badge=self._badge,
            nudge_text=self._nudge_text,
            nudge_opacity=nudge_opacity,
            turn_stage=self._turn_stage if self._attention_state == AttentionState.SULKING else None,
            streak=self._streak,
            focused=self._focused,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.interacted.emit()
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        elif event.button() == Qt.RightButton:
            if self._context_menu_requested_callback:
                self._context_menu_requested_callback(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            if (new_pos - self.pos()).manhattanLength() > _DRAG_THRESHOLD:
                self._drag_moved = True
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            was_plain_click = not self._drag_moved
            self._dragging = False
            if was_plain_click and self._view_mode == "pet":
                self.plain_clicked.emit()
            event.accept()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.moved.emit(self.pos())
