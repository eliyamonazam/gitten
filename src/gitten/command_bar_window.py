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

**v1.14**: the backdrop used to be a dark, near-opaque HUD-style panel with
no relation to `theme.py` (which didn't exist yet). It's now `theme.py`'s
own light warm-card palette -- the same `SURFACE_CARD` fill and `RADIUS`
corner radius every themed `QLineEdit` in Settings uses -- with an `ACCENT`
border rather than `theme.py`'s resting `BORDER` tone, since this bar is
only ever on screen while its input already has real keyboard focus (it
hides itself on focus-out), the same visual state Settings' own
`QLineEdit:focus` rule turns coral for. `theme.py`'s plain `QColor`
constants are used directly in the `QPainter` calls below, not a second set
of hardcoded hex strings that happen to look similar -- see
DEVELOPMENT_NOTES.md's v1.14 entry.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from gitten import theme

COMMAND_BAR_WIDTH = 260
COMMAND_BAR_HEIGHT = 40

# The backdrop's visual style, sourced directly from theme.py's plain
# constants (see the module docstring) so this popup shares its palette,
# corner-radius, and spacing with Settings/Dashboard instead of the old
# unrelated dark-panel look.
_BACKDROP_COLOR = theme.SURFACE_CARD
_BORDER_COLOR = theme.ACCENT
_CORNER_RADIUS = theme.RADIUS
# Padding between the window edge and the QLineEdit, so the rounded
# backdrop shows a clear margin all the way around the text rather than
# being flush with it.
_PADDING = theme.SPACING_SM


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
        # theme.TEXT_PRIMARY/ACCENT text/selection against the light
        # SURFACE_CARD backdrop paintEvent draws below; the QLineEdit itself
        # stays fully transparent so the rounded backdrop shows through
        # around it. theme.py's constants are pulled in directly (via
        # `.name()`) rather than a second hardcoded set of hex strings.
        self._input.setStyleSheet(
            f"background: transparent; color: {theme.TEXT_PRIMARY.name()}; border: none;"
            f'font-family: "{theme.FONT_FAMILY}"; font-size: {theme.FONT_SIZE_BASE}px;'
            f"selection-background-color: {theme.ACCENT.name()}; selection-color: white;"
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
