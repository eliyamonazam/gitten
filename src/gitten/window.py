"""The transparent, always-on-top, frameless kitten widget."""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from gitten.mood import Mood
from gitten.sprite import paint_kitten
from gitten.status_badge import Badge

WINDOW_SIZE = 130
ANIMATION_INTERVAL_MS = 33  # ~30 fps
TASKBAR_MARGIN = 4
_DRAG_THRESHOLD = 4
NUDGE_DURATION_SECONDS = 4.0
_NUDGE_FADE_SECONDS = 1.0


class KittenWindow(QWidget):
    moved = Signal(QPoint)

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
        self._nudge_text: str | None = None
        self._nudge_started_at: float | None = None
        self._start_time = time.monotonic()
        self._dragging = False
        self._drag_moved = False
        self._drag_offset = QPoint()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(ANIMATION_INTERVAL_MS)

        self._context_menu_requested_callback = None

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

    def show_nudge(self, text: str) -> None:
        self._nudge_text = text
        self._nudge_started_at = time.monotonic()

    def set_context_menu_callback(self, callback) -> None:
        self._context_menu_requested_callback = callback

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
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
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
            self._dragging = False
            event.accept()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.moved.emit(self.pos())
