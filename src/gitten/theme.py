"""Gitten's shared design system (v1.13) -- the single source of truth for
color, typography, and spacing that `settings_window.py` and
`dashboard_window.py` both style themselves from, the same "shared
infrastructure built once, reused everywhere" discipline `particles.
ParticleSystem` already established for the drag-trail/shooting-star/
catch-effect features.

## Audit, done before inventing anything

Every color already in use across this codebase, found by grepping for
`QColor(`/hex literals before picking a single new one:

- The cat's own coral body (`sprite.BODY_COLOR` `#E8935F`, highlight
  `#F7B98F`) -- the cat's single most identity-defining color.
- The reminder-alert amber (`sprite._ALERT_FILL_COLOR` `#FFF3E0` /
  `_ALERT_BORDER_COLOR` `#FB8C00`), itself already reused from the
  low-battery badge color per its own v1.10 dev-notes entry -- this
  codebase already has exactly one established "pay attention" tone, not
  two competing ones, so it's reused again here rather than replaced.
- The heatmap's four green shades (`dashboard_window._HEATMAP_COLORS`) and
  empty-day gray (`_HEATMAP_EMPTY_COLOR`) -- meaningful data encoding, left
  untouched by this round per the spec.
- The near-black outline/text color used throughout the sprite
  (`sprite.OUTLINE_COLOR` `#2C2C2A`) and the dark translucent overlay
  backdrops (`command_bar_window._BACKDROP_COLOR`, `window.py`'s inbox
  panel, both `rgba(32, 32, 36, ...)`) -- both explicitly out of scope this
  round (overlays/command bar), but `OUTLINE_COLOR` specifically is worth
  reusing for text below (see TEXT_PRIMARY).
- A scatter of one-off badge/accessory colors with no shared home
  (critical-battery red `#E53935`, charging yellow `#FDD835`, high-resource
  blue `#4FC3F7`, disk gray `#B0BEC5`, streak-star gold `#FFD700`,
  purr-heart pink `#F06292`, particle gold `#FFD54F`) -- exactly what the
  spec means by "every colored element chosen locally, one feature at a
  time, with no central place tying them together."

## What this file defines, and what it deliberately doesn't

A palette for **Settings and Dashboard only**, per `GITTEN_V1_13_SPEC.md`
Part 2's explicit scope -- normal, opaque, light-themed windows, distinct
from the dark translucent overlays (command bar, inbox panel) and the cat
sprite itself, neither of which this round touches. The palette still has
to feel like it belongs to the *same app* as that coral cat, though, so the
primary accent below is the cat's own body color, not an invented new
brand color -- opening Settings or Dashboard should read as "the same
cat's control panel," not an unrelated app that happens to ship alongside
it.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton

# -- Palette ------------------------------------------------------------

# Primary accent: the cat's own coral body color, reused verbatim rather
# than reinvented -- see the module docstring for the v1.13 audit that
# picked this value from what was then `sprite.BODY_COLOR`. As of v1.15
# the relationship runs the other way: `sprite.BODY_COLOR` is now literally
# `theme.ACCENT` (imported from here), the last piece of the v1.13-v1.15
# visual-polish plan tying the character itself into this same palette --
# this is still the one place the actual value is defined.
ACCENT = QColor("#E8935F")
ACCENT_HOVER = QColor("#DC7F45")  # a touch darker/more saturated, for :hover
ACCENT_PRESSED = QColor("#C96B32")  # darker again, for :pressed
ACCENT_SOFT = QColor("#FBE4D3")  # ACCENT lightened toward white, for selected-item highlights

# Secondary/warning accent: reuses the existing reminder-alert amber
# (sprite._ALERT_FILL_COLOR / _ALERT_BORDER_COLOR) -- see the module
# docstring for why this isn't a second, competing "attention" color.
WARNING_BORDER = QColor("#FB8C00")
WARNING_FILL = QColor("#FFF3E0")

# Surfaces (light theme): a plain white card floating on a very faint warm
# page background -- warm rather than neutral gray specifically so the
# window still reads as related to the coral accent even in the large
# areas where no accent color is actually on screen.
SURFACE_PAGE = QColor("#FBF7F4")
SURFACE_CARD = QColor("#FFFFFF")
SURFACE_INSET = QColor("#F4EFEA")  # list widgets / the heatmap's own background -- one step down from the card
BORDER = QColor("#E4DCD3")

# Text: TEXT_PRIMARY reuses sprite.OUTLINE_COLOR (`#2C2C2A`) verbatim -- the
# exact same near-black already used for the cat's own outline and every
# mood face, so body text and the cat's linework share one "ink" color
# instead of two different near-blacks existing side by side in the app.
TEXT_PRIMARY = QColor("#2C2C2A")
TEXT_SECONDARY = QColor("#8A8078")

# -- Typography -----------------------------------------------------------

FONT_FAMILY = "Segoe UI"
FONT_SIZE_BASE = 13

# -- Spacing / shape --------------------------------------------------------

SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 14
RADIUS = 8  # one standard corner radius, used everywhere (buttons, inputs, lists, tab pane)
RADIUS_SM = 4  # a tighter radius for small nested elements (list rows)


def _hex(color: QColor) -> str:
    return color.name()


# A QSS attribute selector (`[primary="true"]`), not a second widget class
# or a per-window stylesheet fragment -- `mark_primary_button` below just
# sets the dynamic property; this one shared stylesheet already knows how
# to render it, on any button in any themed window.
STYLESHEET = f"""
QDialog {{
    background-color: {_hex(SURFACE_PAGE)};
    font-family: "{FONT_FAMILY}";
    font-size: {FONT_SIZE_BASE}px;
    color: {_hex(TEXT_PRIMARY)};
}}

QLabel {{
    color: {_hex(TEXT_PRIMARY)};
    background: transparent;
}}

QLabel[sectionHeader="true"] {{
    color: {_hex(ACCENT_PRESSED)};
    font-weight: 600;
}}

QLabel[muted="true"] {{
    color: {_hex(TEXT_SECONDARY)};
}}

QTabWidget::pane {{
    border: 1px solid {_hex(BORDER)};
    border-radius: {RADIUS}px;
    background-color: {_hex(SURFACE_CARD)};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {_hex(SURFACE_PAGE)};
    color: {_hex(TEXT_SECONDARY)};
    padding: {SPACING_SM}px {SPACING_MD}px;
    border: 1px solid {_hex(BORDER)};
    border-bottom: none;
    border-top-left-radius: {RADIUS}px;
    border-top-right-radius: {RADIUS}px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {_hex(SURFACE_CARD)};
    color: {_hex(ACCENT_PRESSED)};
    font-weight: 600;
}}

QTabBar::tab:hover:!selected {{
    color: {_hex(ACCENT)};
}}

QPushButton {{
    background-color: {_hex(SURFACE_CARD)};
    color: {_hex(TEXT_PRIMARY)};
    border: 1px solid {_hex(BORDER)};
    border-radius: {RADIUS}px;
    padding: {SPACING_SM}px {SPACING_MD}px;
}}

QPushButton:hover {{
    border-color: {_hex(ACCENT)};
    color: {_hex(ACCENT_PRESSED)};
}}

QPushButton:pressed {{
    background-color: {_hex(SURFACE_INSET)};
}}

QPushButton[primary="true"] {{
    background-color: {_hex(ACCENT)};
    color: white;
    border: none;
    font-weight: 600;
}}

QPushButton[primary="true"]:hover {{
    background-color: {_hex(ACCENT_HOVER)};
}}

QPushButton[primary="true"]:pressed {{
    background-color: {_hex(ACCENT_PRESSED)};
}}

QLineEdit, QSpinBox {{
    background-color: {_hex(SURFACE_CARD)};
    border: 1px solid {_hex(BORDER)};
    border-radius: {RADIUS}px;
    padding: {SPACING_XS}px {SPACING_SM}px;
    color: {_hex(TEXT_PRIMARY)};
    selection-background-color: {_hex(ACCENT)};
    selection-color: white;
}}

QLineEdit:focus, QSpinBox:focus {{
    border: 1px solid {_hex(ACCENT)};
}}

QListWidget {{
    background-color: {_hex(SURFACE_INSET)};
    border: 1px solid {_hex(BORDER)};
    border-radius: {RADIUS}px;
    padding: {SPACING_XS}px;
    outline: none;
}}

QListWidget::item {{
    padding: {SPACING_XS}px {SPACING_SM}px;
    border-radius: {RADIUS_SM}px;
    color: {_hex(TEXT_PRIMARY)};
}}

QListWidget::item:selected {{
    background-color: {_hex(ACCENT_SOFT)};
    color: {_hex(TEXT_PRIMARY)};
}}

QListWidget::item:hover:!selected {{
    background-color: {_hex(SURFACE_CARD)};
}}
"""


def apply_theme(widget) -> None:
    """Apply the shared stylesheet to a top-level themed window (Settings,
    Dashboard). QSS cascades to every child automatically, so this is the
    one call each window's `__init__` needs -- no per-widget styling calls
    scattered through the rest of the file."""
    widget.setStyleSheet(STYLESHEET)


def mark_primary_button(button: QPushButton) -> None:
    """Tag a button as this screen's one primary action (e.g. each
    settings tab's own Save button) so the shared stylesheet's
    `QPushButton[primary="true"]` rule picks it out from ordinary
    secondary buttons (Add/Remove/Close/Cancel) -- giving each screen one
    clear, coral, unmissable action instead of a wall of identically
    colored buttons. Safe to call before or after `apply_theme` runs."""
    button.setProperty("primary", True)
    style = button.style()
    style.unpolish(button)
    style.polish(button)


def mark_section_header(label) -> None:
    """Tag a QLabel as a section header (e.g. "Distracting window
    titles:", "System:") so it picks up the shared stylesheet's bolder,
    accent-tinted `sectionHeader` styling instead of blending into
    ordinary body text."""
    label.setProperty("sectionHeader", True)
    style = label.style()
    style.unpolish(label)
    style.polish(label)


def mark_muted_label(label) -> None:
    """Tag a QLabel as secondary/transient text (a "Saved." confirmation,
    a small explanatory note) so it reads as lower-priority than the
    surrounding primary-colored body text instead of competing with it."""
    label.setProperty("muted", True)
    style = label.style()
    style.unpolish(label)
    style.polish(label)
