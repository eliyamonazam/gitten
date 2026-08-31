"""The quick command bar popup (v1.9): a small single-line input summoned
by the global hotkey near the cat's current position. Enter submits the
typed text (raw -- parsing/dispatch happens in main.py via `commands.py`,
this window doesn't need to know what a "command" even is); Escape or
losing focus closes it without submitting -- standard command-palette
behavior.

This window is entirely self-contained and never touches `KittenWindow`'s
own `view_mode`/click-handling state machine -- it's a separate popup, not
a mode of the existing window, the same "own file, own state" split
`mouse_window.py` already established for the v1.7 chase minigame's mouse
sprite.

Reuses the transparent/always-on-top/frameless flag combination already
proven by `KittenWindow`/`MouseWindow`, but *without*
`Qt.WindowDoesNotAcceptFocus` / `Qt.WA_ShowWithoutActivating` -- unlike
those two windows, this one is a real text box and has to actually receive
keyboard focus to be usable, so it can't reuse those two focus-suppressing
flags verbatim.

The visible rounded backdrop behind the input is painted directly with
`QPainter` in `paintEvent`, the same way every other transparent top-level
window in this codebase (`KittenWindow`/`sprite.py`, `MouseWindow`) draws
its own visuals -- **not** a QSS `background-color` on the bare `QWidget`
itself, which was tried first and turned out invisible: a plain `QWidget`
never actually paints its stylesheet's background/border unless
`Qt.WA_StyledBackground` is also set (widgets like `QPushButton`/`QLabel`
get this for free from their own default `paintEvent`, a bare `QWidget`
does not) -- see DEVELOPMENT_NOTES.md's v1.9 bugfix entry for how this was
caught and confirmed live.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

COMMAND_BAR_WIDTH = 260
COMMAND_BAR_HEIGHT = 40

# The backdrop's visual style -- a near-opaque dark rounded panel with a
# faint lighter border, matching the inbox panel's dark-panel palette
# (window.py's `_build_inbox_panel`) so the popup reads as part of the same
# app rather than a mismatched new look.
_BACKDROP_COLOR = QColor(32, 32, 36, 235)
_BORDER_COLOR = QColor(110, 110, 118, 255)
_CORNER_RADIUS = 10
# Padding between the window edge and the QLineEdit, so the rounded
# backdrop shows a clear margin all the way around the text rather than
# being flush with it.
_PADDING = 8


class CommandBarWindow(QWidget):
    # Emitted with the raw typed text on Enter, after the bar has already
    # closed itself.
    command_submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(COMMAND_BAR_WIDTH, COMMAND_BAR_HEIGHT)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("type a command... (help)")
        # High-contrast white text/selection against the dark backdrop
        # paintEvent draws below; the QLineEdit itself stays fully
        # transparent so the rounded backdrop shows through around it.
        self._input.setStyleSheet(
            "background: transparent; color: white; border: none;"
            "font-size: 14px; selection-background-color: #4a90d9;"
            "selection-color: white;"
        )
        self._input.returnPressed.connect(self._submit)
        self._input.installEventFilter(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(_PADDING, _PADDING, _PADDING, _PADDING)
        layout.addWidget(self._input)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(_BORDER_COLOR)
        painter.setBrush(_BACKDROP_COLOR)
        # Inset by 1px so the 1px border itself doesn't get clipped at the
        # window edge.
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), _CORNER_RADIUS, _CORNER_RADIUS)

    def show_near(self, x: int, y: int) -> None:
        """Show the bar at (x, y) -- already clamped to the screen by the
        caller -- clear any previously typed text, and hand it real
        keyboard focus."""
        self._input.clear()
        self.move(int(x), int(y))
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus(Qt.ActiveWindowFocusReason)

    def _submit(self) -> None:
        text = self._input.text()
        self.hide()
        self.command_submitted.emit(text)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._input:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key_Escape:
                self.hide()
                return True
            if event.type() == QEvent.Type.FocusOut:
                self.hide()
        return super().eventFilter(watched, event)
