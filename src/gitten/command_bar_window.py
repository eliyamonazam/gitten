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
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

COMMAND_BAR_WIDTH = 260
COMMAND_BAR_HEIGHT = 40


class CommandBarWindow(QWidget):
    # Emitted with the raw typed text on Enter, after the bar has already
    # closed itself.
    command_submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(COMMAND_BAR_WIDTH, COMMAND_BAR_HEIGHT)

        self.setObjectName("commandBar")
        self.setStyleSheet(
            "#commandBar { background-color: rgba(32, 32, 36, 235); border-radius: 8px; }"
        )

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("type a command... (help)")
        self._input.setStyleSheet(
            "background: transparent; color: white; border: none;"
            "font-size: 14px; padding: 0 10px;"
        )
        self._input.returnPressed.connect(self._submit)
        self._input.installEventFilter(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._input)

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
