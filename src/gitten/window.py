"""The transparent, always-on-top, frameless kitten widget."""

from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
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
from gitten.particles import ParticleSystem
from gitten.seasons import is_night_time
from gitten.sprite import draw_particles, paint_kitten
from gitten.status_badge import Badge

WINDOW_SIZE = 130
INBOX_SIZE = QSize(240, 300)
ANIMATION_INTERVAL_MS = 33  # ~30 fps
TASKBAR_MARGIN = 4
_DRAG_THRESHOLD = 4
NUDGE_DURATION_SECONDS = 4.0
_NUDGE_FADE_SECONDS = 1.0

# Spawn a drag-trail sparkle roughly every other animation frame, not on
# every mouseMoveEvent (which can fire far more often than the 30fps repaint
# timer during a fast drag).
_DRAG_PARTICLE_INTERVAL_SECONDS = 2 * ANIMATION_INTERVAL_MS / 1000.0
_DRAG_PARTICLE_LIFESPAN_SECONDS = 0.5

_SHOOTING_STAR_LIFESPAN_SECONDS = 1.0

# The cursor has to sit on the cat for a moment before it purrs, so a mouse
# just passing over it on its way somewhere else doesn't trigger the purr
# face for a single frame.
_HOVER_PURR_DELAY_MS = 200

_HIGH_FIVE_DURATION_SECONDS = 1.3

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
        self._accessory: str | None = None
        self._nudge_text: str | None = None
        self._nudge_started_at: float | None = None
        self._start_time = time.monotonic()
        self._dragging = False
        self._drag_moved = False
        self._drag_offset = QPoint()
        self._particles = ParticleSystem()
        self._last_particle_spawn_at = 0.0
        self._hovering = False
        # Purring only kicks in once the cursor has held still over the cat
        # for _HOVER_PURR_DELAY_MS -- entering starts this single-shot timer
        # rather than setting _hovering immediately; leaving cancels it (and
        # any active purr) right away, no delay needed on the way out.
        self._hover_purr_timer = QTimer(self)
        self._hover_purr_timer.setSingleShot(True)
        self._hover_purr_timer.timeout.connect(self._on_hover_purr_delay_elapsed)

        # Single/double-click disambiguation (Feature 5): a double-click is,
        # at the Qt event level, still a single click first -- Qt delivers
        # press/release/press/doubleClick/release in that order. So a plain
        # click's action (open inbox / register a pet) is never applied
        # immediately on release; it's deferred behind this timer, using the
        # same interval Qt itself uses to detect double-clicks, so a genuine
        # second click is always guaranteed to arrive (and cancel it) first.
        self._click_pending_timer = QTimer(self)
        self._click_pending_timer.setSingleShot(True)
        self._click_pending_timer.timeout.connect(self._on_click_confirmed_single)
        self._just_double_clicked = False
        self._high_fiving = False

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

    def set_accessory(self, accessory: str | None) -> None:
        if accessory != self._accessory:
            self._accessory = accessory
            self.update()

    def show_nudge(self, text: str) -> None:
        self._nudge_text = text
        self._nudge_started_at = time.monotonic()

    @property
    def is_nudging(self) -> bool:
        return self._nudge_text is not None

    def trigger_shooting_star(self) -> None:
        """A single particle (Feature 1's system, reused unchanged) launched
        from the top-left corner and animated diagonally to the bottom-right
        over ~1 second, fading as it goes -- the rare event `main.py` plays
        instead of a one-liner roughly 5% of the time."""
        now = time.monotonic()
        origin = self.mapToGlobal(QPoint(0, 0))
        dx = self.width() / _SHOOTING_STAR_LIFESPAN_SECONDS
        dy = self.height() / _SHOOTING_STAR_LIFESPAN_SECONDS
        self._particles.spawn_particle(
            float(origin.x()),
            float(origin.y()),
            now,
            lifespan=_SHOOTING_STAR_LIFESPAN_SECONDS,
            dx=dx,
            dy=dy,
        )

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

        # Particles are tracked in *global* screen coordinates (see
        # _maybe_spawn_drag_particle / trigger_shooting_star) so a sparkle
        # stays put on screen while the window itself moves away from it
        # during a drag -- that's what makes the drag trail actually trail
        # instead of snapping along rigidly with the widget. They're
        # converted back to local widget-pixel space here, at paint time,
        # outside paint_kitten's own 128x128 canvas transform (particles are
        # cosmetic, window-owned overlay, not part of the kitten's internal
        # drawing space).
        self._particles.update_and_prune(now)
        origin = self.mapToGlobal(QPoint(0, 0))
        local_positions = [
            (x - origin.x(), y - origin.y(), opacity)
            for x, y, opacity in self._particles.positions(now)
        ]
        draw_particles(painter, local_positions)

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
            hovering=self._hovering,
            high_five=self._high_fiving,
            accessory=self._accessory,
            night=is_night_time(datetime.now().hour),
        )

    def enterEvent(self, event) -> None:
        self._hover_purr_timer.start(_HOVER_PURR_DELAY_MS)

    def leaveEvent(self, event) -> None:
        self._hover_purr_timer.stop()
        self._hovering = False

    def _on_hover_purr_delay_elapsed(self) -> None:
        self._hovering = True

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
            self._maybe_spawn_drag_particle(event)
            event.accept()

    def _maybe_spawn_drag_particle(self, event: QMouseEvent) -> None:
        now = time.monotonic()
        if now - self._last_particle_spawn_at < _DRAG_PARTICLE_INTERVAL_SECONDS:
            return
        self._last_particle_spawn_at = now
        # Global (screen), not local (widget) coordinates -- see the
        # comment in paintEvent for why: this is what makes the sparkle stay
        # behind at the cursor's actual on-screen spot as the window moves
        # away from it, instead of being dragged along rigidly with the
        # widget.
        global_pos = event.globalPosition()
        self._particles.spawn_particle(
            global_pos.x(), global_pos.y(), now, lifespan=_DRAG_PARTICLE_LIFESPAN_SECONDS
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            was_plain_click = not self._drag_moved
            self._dragging = False
            if self._just_double_clicked:
                # This is the trailing release of a double-click we already
                # handled in mouseDoubleClickEvent -- don't also queue up a
                # single-click action for it.
                self._just_double_clicked = False
            elif was_plain_click and self._view_mode == "pet":
                # Don't act yet -- a genuine double-click may still arrive.
                # See the disambiguation comment in __init__.
                self._click_pending_timer.start(QApplication.doubleClickInterval())
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._view_mode == "pet":
            self._click_pending_timer.stop()
            self._just_double_clicked = True
            self._trigger_high_five()
            event.accept()

    def _on_click_confirmed_single(self) -> None:
        """The pending-click timer elapsed with no second click arriving --
        this really was a single click, so now (and only now) it counts."""
        self.plain_clicked.emit()

    def _trigger_high_five(self) -> None:
        self._high_fiving = True
        self.update()
        QTimer.singleShot(int(_HIGH_FIVE_DURATION_SECONDS * 1000), self._clear_high_five)

    def _clear_high_five(self) -> None:
        self._high_fiving = False
        self.update()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.moved.emit(self.pos())
