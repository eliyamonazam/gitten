"""A small transparent/always-on-top window showing the mouse (rodent)
sprite for the v1.7 chase minigame.

Copies `KittenWindow`'s window-flag setup verbatim (see v1's `window.py`)
-- no new window-flag research needed, this combination is already proven
to work on this platform. Carries none of `KittenWindow`'s interaction
logic (no dragging, no click handling, no view modes, no context menu): it
only ever needs to be shown at a position and hidden again.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget

from gitten.sprite import paint_mouse

MOUSE_WINDOW_SIZE = 48
ANIMATION_INTERVAL_MS = 33  # ~30fps, matches KittenWindow


class MouseWindow(QWidget):
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
        self.resize(MOUSE_WINDOW_SIZE, MOUSE_WINDOW_SIZE)

        self._start_time = time.monotonic()

        # Purely so the sprite's gentle breathing animation has a `t` to
        # animate against -- the same idiom KittenWindow's own timer uses,
        # just for a much simpler sprite with no interaction to drive.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(ANIMATION_INTERVAL_MS)

    def show_at(self, x: int, y: int) -> None:
        self.move(int(x), int(y))
        self.show()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        rect = QRectF(0, 0, self.width(), self.height())
        elapsed = time.monotonic() - self._start_time
        paint_mouse(painter, rect, elapsed)
