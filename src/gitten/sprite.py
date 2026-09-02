"""Drawing code for the kitten and mouse sprites -- `paint_kitten`/
`paint_mouse` are pure with respect to Qt widget state: give either one a
painter, a target rect, the relevant mood/pose flags, and a monotonically
increasing time in seconds, and it draws one animated frame. No external
art assets or files; everything (including the pixel-art frame data below)
lives in this module.

## v1.16 -- a genuine pixel-art redesign (Phase 4)

Per `GITTEN_V1_16_SPEC.md`, this round fully replaces v1.15's flat-mascot
*vector* rendering (smooth `QPainterPath` shapes) with real pixel art:
every pose is now a small, fixed logical grid (`pixelart.Frame` -- see that
module for the rendering engine itself, built and verified in isolation
first per the spec's Part 0) of flat-filled squares, upscaled with
nearest-neighbor (`Qt.FastTransformation`) scaling for crisp, hard pixel
edges. Poses that used to breathe/sway/blink via a continuous sine wave now
do it via a small, fixed set of discrete frames swapped on a timer instead
(`pixelart.frame_index`) -- a real technique change, not a re-skin, per the
spec's own framing. What did **not** change: precedence between poses
(away > sulk > purr > curious > focused > plain mood), *when* each pose is
shown, or anything that's about the cat's on-screen *position* rather than
its own drawn frame (the window's drag/walk movement, the particle
system's drift/fade, bubble entrance/fade timing, a badge's alpha pulse) --
all of that keeps its exact pre-v1.16 continuous timing, per the spec's own
"what does NOT need to change" note.

Every grid below was designed from scratch for this project (a small,
original chibi-cat/mouse silhouette and an original palette-key grid
convention) -- inspired by the pixel-art desktop-pet genre broadly, not
derived from or referencing any specific existing project's sprites,
palette, or character names, per the spec's explicit originality note.

See `DEVELOPMENT_NOTES.md`'s v1.16 entry for the part-by-part build order,
the Part 0 isolation verification, and the live-screenshot verification for
each part.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)

from gitten import pixelart, theme
from gitten.mood import Mood
from gitten.status_badge import Badge

# The cat's own body color *is* theme.ACCENT (not an independent copy of the
# same hex) -- unchanged from v1.15, still the anchor tying the character
# itself into the same palette as Settings/Dashboard/command bar/bubbles.
BODY_COLOR = theme.ACCENT
# Flat secondary tone for small two-tone pixel details (inner ear, paw pad).
SECONDARY_FILL_COLOR = theme.ACCENT_SOFT
# The one outline/ink color used throughout every grid below.
OUTLINE_COLOR = theme.TEXT_PRIMARY
WHITE = theme.SURFACE_CARD
SHADOW_COLOR = QColor(0, 0, 0, 60)
ZZZ_COLOR = QColor(120, 120, 128, 220)

CANVAS = 128.0
CENTER = QPointF(CANVAS / 2, 70.0)
BODY_RX, BODY_RY = 34.0, 30.0

# Still used by the speech bubble's border and the alarm-clock icon inside
# it -- both v1.14-era UI chrome, explicitly out of this round's scope (the
# spec's own "the cat/mouse sprite art" scope, not the bubble card itself).
_OUTLINE_PEN_WIDTH = 3.2


def _outline_pen(width: float = _OUTLINE_PEN_WIDTH) -> QPen:
    pen = QPen(OUTLINE_COLOR)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


_MOONLIT_BASE = QColor("#3B4A6B")
_NIGHT_BLEND_FACTOR = 0.45


def _blend_color(a: QColor, b: QColor, factor: float) -> QColor:
    """Linear-interpolate two colors; factor 0.0 = a, 1.0 = b. Unchanged
    from v1.15 -- still how night-mode tints a color, just applied to a
    palette entry now instead of a vector fill."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * factor),
        round(a.green() + (b.green() - a.green()) * factor),
        round(a.blue() + (b.blue() - a.blue()) * factor),
    )


# -- the cat's pixel-art palette --------------------------------------------
# Four colors total (outline, body, a secondary tone for inner-ear/paw
# details, and eye-white) -- within the spec's "roughly 4-6 colors" budget.
# Night-mode swaps only the body entry, the same single value `_blend_color`
# has always adjusted.

_CAT_PALETTE_BASE: pixelart.Palette = {
    "O": OUTLINE_COLOR.name(),
    "B": BODY_COLOR.name(),
    "C": SECONDARY_FILL_COLOR.name(),
    "W": WHITE.name(),
}


def _cat_palette(night: bool) -> pixelart.Palette:
    if not night:
        return _CAT_PALETTE_BASE
    blended = _blend_color(BODY_COLOR, _MOONLIT_BASE, _NIGHT_BLEND_FACTOR)
    return {**_CAT_PALETTE_BASE, "B": blended.name()}


# -- cat pixel-art frames ----------------------------------------------------
# A 32x32 logical grid (per the spec's own suggestion) holding the *whole*
# character (body+ears+tail+face) per frame -- composed by hand at design
# time in the same back-to-front order the old vector code drew in (tail,
# then ears, then the body last so it covers both roots, then the face on
# top), so a body silhouette drawn last still reads as "ears growing out of
# the head" and "a tail rooted at the flank" exactly like before, just as
# flat-filled squares instead of smooth paths.

_F_idle_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    ".....OBBBBBOOOBBBBBOOOBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOOOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_idle_1 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO..O.OCCCCCCO......",
    ".....OOCCCCOOOOOBOOOOOCCCOO...OO",
    ".....OOOOOOBBBBBBBBBBBOOOOO..OOB",
    "........OOBBBBBBBBBBBBBOO....OBB",
    ".......OBBBBBBBBBBBBBBBBBO...OBB",
    "......OBBBBBBBBBBBBBBBBBBBO..OBB",
    "......OBBBBBBBBBBBBBBBBBBBO..OBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBO.OBB",
    ".....OBBBBBBOBBBBBBBOBBBBBBOOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    ".....OBBBBBBBBBOOOBBBBBBBBBOBBBB",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBB",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBB",
    ".......OBBBBBBBBBBBBBBBBBOBBBBBO",
    "........OOBBBBBBBBBBBBBOOBBBBBBO",
    ".........OOBBBBBBBBBBBOOBBBBBBOO",
    "...........OOOOOBOOOOO..OBBBBOO.",
    "................O........OOOO...",
    "................................",
    "................................",
    "................................",
)
_IDLE_FRAMES: tuple[pixelart.Frame, ...] = (_F_idle_0, _F_idle_1)
_IDLE_FRAME_SECONDS = 1.4

_F_happy_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBBOBBBBBBBOBBBBBOOBBBO",
    ".....OBBBBBOBOBBBBBOBOBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBOBBBOBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOBOBBBBBBBBBOBBBO",
    "......OBBBBBBBBBOBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_happy_1 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO..O.OCCCCCCO......",
    ".....OOCCCCOOOOOBOOOOOCCCOO...OO",
    ".....OOOOOOBBBBBBBBBBBOOOOO..OOB",
    "........OOBBBBBBBBBBBBBOO....OBB",
    ".......OBBBBBBBBBBBBBBBBBO...OBB",
    "......OBBBBBBBBBBBBBBBBBBBO..OBB",
    "......OBBBBBBBBBBBBBBBBBBBO..OBB",
    ".....OBBBBBBOBBBBBBBOBBBBBBO.OBB",
    ".....OBBBBBOBOBBBBBOBOBBBBBOOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    ".....OBBBBBBBBOBBBOBBBBBBBBOBBBB",
    "......OBBBBBBBBOBOBBBBBBBBOBBBBB",
    "......OBBBBBBBBBOBBBBBBBBBOBBBBB",
    ".......OBBBBBBBBBBBBBBBBBOBBBBBO",
    "........OOBBBBBBBBBBBBBOOBBBBBBO",
    ".........OOBBBBBBBBBBBOOBBBBBBOO",
    "...........OOOOOBOOOOO..OBBBBOO.",
    "................O........OOOO...",
    "................................",
    "................................",
    "................................",
)
_HAPPY_FRAMES: tuple[pixelart.Frame, ...] = (_F_happy_0, _F_happy_1)
_HAPPY_FRAME_SECONDS = 1.4

_F_waiting_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBOBBBBBOBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBOWWBBBBBOWWBBBBOOBBBO",
    ".....OBBBBBOWWBBBBBOWWBBBBBOBBBO",
    ".....OBBBBBWWOBBBBBWWOBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBOBOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBOBOBOBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_waiting_1 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBOBBBBBOBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBOWWBBBBBOWWBBBBOOBBBO",
    ".....OBBBBBWWOBBBBBWWOBBBBBOBBBO",
    ".....OBBBBBWWOBBBBBWWOBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBOBOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBOBOBOBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_WAITING_FRAMES: tuple[pixelart.Frame, ...] = (_F_waiting_0, _F_waiting_1)
# A brisker cadence than idle's slow breathing -- reads as the nervous
# side-to-side glance the old continuous sine used to animate, now as a
# discrete 2-frame swap between the pupils' left/right position.
_WAITING_FRAME_SECONDS = 0.6

_F_away_0 = (
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "................................",
    "......OO................OO......",
    "......CCO..............OCC......",
    ".....OCCO..............OCCO.....",
    "....OCCCCO......O.....OCCCCO....",
    "....OCCCOOOOOOOOBOOOOOOOCCCO....",
    "...OOOOOOOBBBBBBBBBBBBBOOOOOO...",
    "......OOBBOOOOOBBBOOOOOBBOO.....",
    ".....OBBBBBBBBBBBBBBBBBBBBBO....",
    "....OBBBBBBBBBBBBBBBBBBBBOOBOO..",
    "....OBBBBBBBBBBBBBBBBBBBBOBBBO..",
    "...OBBBBBBBBBBBBBBBBBBBBBBBBBB..",
    "....OBBBBBBBBBBBOBBBOBOBBOBBBO..",
    "....OBBBBBBBBBBBBBBBBBBOOOBBBO..",
    ".....OBBBBBBBBBBBBBBOBBBBBBBBO..",
    "......OOBBBBBBBBBBBBOBBBBBBBBO..",
    ".......OOOBBBBBBBBBBBOBBBBBBBO..",
    "..........OOOOOOBOOOOOOOBBBBO...",
    "................O......OOOOO....",
    "................................",
    "................................",
    "................................",
    "................................",
)
_AWAY_FRAMES: tuple[pixelart.Frame, ...] = (_F_away_0,)
_AWAY_FRAME_SECONDS = 3.0

_F_sulk0_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBOBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBOBBBBBBBBBOOBBBO",
    "......OBBBBBBBBBOBBBBBBBBBOOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBOBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_sulk1_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBOBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBOBBBBBBBBBOOBBBO",
    "......OBBBBBBBBBOBBBBBBBBBOOBBBO",
    ".....OBBBBBBBBBBOBBOOOBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBOBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_sulk2_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    ".....OBBBBOOOOOBBBOOOOOBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_sulk3_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    ".....OBBBBOOOOOBBBOOOOOBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOOOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
# Sulking/reconciliation stages 0-3 -- "fully reconciled" (the old code's
# stage 4) is just the plain front-facing IDLE frames above, handled by the
# caller falling through to them once `turn_stage` goes back to `None`.
_SULK_FRAMES: dict[int, tuple[pixelart.Frame, ...]] = {
    0: (_F_sulk0_0,),
    1: (_F_sulk1_0,),
    2: (_F_sulk2_0,),
    3: (_F_sulk3_0,),
}

_F_purr_0 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO.....",
    ".....OOOOOOOOOOOBOOOOOOOOOO.....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    ".....OBBBBBOOOBBBBBOOOBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOBOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_purr_1 = (
    "................................",
    "................................",
    ".........OO..........OO.........",
    ".........OO..........OO.........",
    "........OCCO........OCCO........",
    "........OCCO........OCCO........",
    ".......OCCCCO......OCCCCO.......",
    ".......OCCCCO......OCCCCO.......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOCCCCCCOO.OOOCCCCCCOO...OO",
    ".....OOOOOOOOOOOBOOOOOOOOOO..OOB",
    ".........OOBBBBBBBBBBBOO.....OBB",
    "........OOBBBBBBBBBBBBBOO....OBB",
    ".......OBBBBBBBBBBBBBBBBBO...OBB",
    "......OBBBBBBBBBBBBBBBBBBBO..OBB",
    "......OBBBBBBBBBBBBBBBBBBBO..OBB",
    ".....OBBBBBOOOBBBBBOOOBBBBBOOBBB",
    ".....OBBBBBBOBBBBBBBOBBBBBBOOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBB",
    ".....OBBBBBBBBBBBBBBBBBBBBBOOBBB",
    ".....OBBBBBBBBBOBOBBBBBBBBBOBBBB",
    ".....OBBBBBBBBBBOBBBBBBBBBBOBBBB",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBB",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBBO",
    "........OOBBBBBBBBBBBBBOOBBBBBOO",
    ".........OOBBBBBBBBBBBOOOBBBBOO.",
    "...........OOOOOBOOOOO...OOOO...",
    "................O...............",
    "................................",
    "................................",
)
_PURR_FRAMES: tuple[pixelart.Frame, ...] = (_F_purr_0, _F_purr_1)
_PURR_FRAME_SECONDS = 0.45

_F_focused_0 = (
    "................................",
    "..........OO........OO..........",
    ".........OCO........OCO.........",
    ".........OCC........CCO.........",
    "........OCCCO......OCCCO........",
    "........OCCCO......OCCCO........",
    ".......OCCCCCO....OCCCCCO.......",
    "......OOCCCCCO....OCCCCCOO......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOOOOOOOOO.OOOOOOOOOOO.....",
    "...........OOOOOBOOOOO..........",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBWWWBBBBBWWWBBBBOOBBBO",
    ".....OBBBBBWOWBBBBBWOWBBBBBOBBBO",
    ".....OBBBBBWWWBBBBBWWWBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOOOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_F_focused_1 = (
    "................................",
    "..........OO........OO..........",
    ".........OCO........OCO.........",
    ".........OCC........CCO.........",
    "........OCCCO......OCCCO........",
    "........OCCCO......OCCCO........",
    ".......OCCCCCO....OCCCCCO.......",
    "......OOCCCCCO....OCCCCCOO......",
    "......OCCCCCCO....OCCCCCCO......",
    ".....OOOOOOOOOO.OOOOOOOOOOO.....",
    "...........OOOOOBOOOOO..........",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBWOWBBBBBWOWBBBBOOBBBO",
    ".....OBBBBBOOOBBBBBOOOBBBBBOBBBO",
    ".....OBBBBBWOWBBBBBWOWBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOOOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_FOCUSED_FRAMES: tuple[pixelart.Frame, ...] = (_F_focused_0, _F_focused_1)
_FOCUSED_FRAME_SECONDS = 0.9

_F_curious_0 = (
    "................................",
    "........OO......................",
    "........CC......................",
    ".......OCCO...........OO........",
    ".......OCCO...........CC........",
    "......OCCCCO.........OCCO.......",
    "......OCCCCO.........OCCO.......",
    ".....OCCCCCCO.......OCCCCO......",
    ".....OCCCCCCO......OOCCCCOO.....",
    "....OOOOOOOOOO..O..OCCCCCCO.....",
    "...........OOOOOBOOOOOOOOOOO....",
    ".........OOBBBBBBBBBBBOO....OOO.",
    "........OOBBBBBBBBBBBBBOO..OOBOO",
    ".......OBBBBBBBBBBBBBBBBBO.OBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOOBBBO",
    "......OBBBBOWOBBBBBOWOBBBBOOBBBO",
    ".....OBBBBBWWOBBBBBWWOBBBBBOBBBO",
    ".....OBBBBBOWOBBBBBOWOBBBBBOBBBO",
    ".....OBBBBBBBBBBBBBBBBBBBBBOBBBO",
    "....OBBBBBBBBBBBBBBBBBBBBBBBOBBO",
    ".....OBBBBBBBBBBOOBBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOWWOBBBBBBBBOBBBO",
    ".....OBBBBBBBBBOWWOBBBBBBBBOBBBO",
    "......OBBBBBBBBBOOBBBBBBBBOBBBBO",
    "......OBBBBBBBBBBBBBBBBBBBOBBBBO",
    ".......OBBBBBBBBBBBBBBBBBOBBBBOO",
    "........OOBBBBBBBBBBBBBOOBBBBOO.",
    ".........OOBBBBBBBBBBBOO.OOOO...",
    "...........OOOOOBOOOOO..........",
    "................O...............",
    "................................",
    "................................",
)
_CURIOUS_FRAMES: tuple[pixelart.Frame, ...] = (_F_curious_0,)
# v1.15's curious pose rotated the head via `painter.rotate` -- rotating a
# nearest-neighbor pixel image by a few degrees would re-smooth its edges
# and defeat the whole point of this round, so instead the tilt is baked
# directly into this one frame's own asymmetric ear/head placement (one ear
# taller and shifted, the other lower) -- a genuine pixel-art technique for
# suggesting a tilt without ever rotating the bitmap itself.
_CURIOUS_FRAME_SECONDS = 1.0

_CAT_GRID_SIZE = 32
# Canvas units per logical pixel, and which grid cell (col, row) lands
# exactly on `center` -- both fixed constants shared by every pose above,
# since every frame was authored into the same absolute 32x32 coordinate
# space regardless of where that particular pose's body sits within it.
_CAT_GRID_PX = 3.4
_CAT_ANCHOR_COL = 16.0
_CAT_ANCHOR_ROW = 19.0


def _cat_sprite_rect(center: QPointF) -> QRectF:
    size = _CAT_GRID_SIZE * _CAT_GRID_PX
    x = center.x() - _CAT_ANCHOR_COL * _CAT_GRID_PX
    y = center.y() - _CAT_ANCHOR_ROW * _CAT_GRID_PX
    return QRectF(x, y, size, size)


def _select_cat_frames(
    show_away: bool,
    turn_stage: int | None,
    show_purr: bool,
    show_curious: bool,
    show_focused: bool,
    mood: Mood,
) -> tuple[tuple[pixelart.Frame, ...], float]:
    """The same precedence order `paint_kitten` has always used (away >
    sulk > purr > curious > focused > plain mood), just picking a frame set
    + discrete-animation timing instead of a set of continuous draw calls."""
    if show_away:
        return _AWAY_FRAMES, _AWAY_FRAME_SECONDS
    if turn_stage is not None:
        return _SULK_FRAMES[turn_stage], _IDLE_FRAME_SECONDS
    if show_purr:
        return _PURR_FRAMES, _PURR_FRAME_SECONDS
    if show_curious:
        return _CURIOUS_FRAMES, _CURIOUS_FRAME_SECONDS
    if show_focused:
        return _FOCUSED_FRAMES, _FOCUSED_FRAME_SECONDS
    if mood == Mood.HAPPY:
        return _HAPPY_FRAMES, _HAPPY_FRAME_SECONDS
    if mood == Mood.WAITING:
        return _WAITING_FRAMES, _WAITING_FRAME_SECONDS
    return _IDLE_FRAMES, _IDLE_FRAME_SECONDS


def paint_kitten(
    painter: QPainter,
    rect: QRectF,
    mood: Mood,
    t: float,
    dragging: bool = False,
    badge: Badge | None = None,
    nudge_text: str | None = None,
    nudge_opacity: float = 0.0,
    nudge_elapsed: float = 0.0,
    nudge_alert: bool = False,
    turn_stage: int | None = None,
    streak: int = 0,
    focused: bool = False,
    hovering: bool = False,
    high_five: bool = False,
    accessory: str | None = None,
    night: bool = False,
    curious: bool = False,
    away: bool = False,
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    scale = min(rect.width(), rect.height()) / CANVAS
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.translate(-CANVAS / 2, -CANVAS / 2)

    # Normally rect.width() == rect.height() == the fixed window size, and
    # this equals CANVAS/2 exactly. But window.py temporarily widens the
    # physical window (keeping height fixed, so `scale` above -- and every
    # other proportion in this whole function -- stays unchanged) to fit a
    # nudge bubble too wide for the plain canvas; this is how much
    # canvas-unit half-width is actually available to draw into for this
    # particular call, used only by the nudge bubble's own clamping below.
    canvas_half_width = rect.width() / (2 * scale)

    # `bob` (a gentle vertical float) and `jitter_x` (the WAITING mood's
    # nervous shiver) are animations of the cat's *position*, not its own
    # drawn frame -- explicitly the kind of thing v1.16 leaves as continuous
    # timing, unchanged from every prior round (see this module's docstring
    # and GITTEN_V1_16_SPEC.md's "what does NOT need to change" note).
    bob = 1.5 * math.sin(t * 2.0) if not dragging else 0.0
    jitter_x = 0.6 * math.sin(t * 14.0) if mood == Mood.WAITING and not away else 0.0
    center = QPointF(CENTER.x() + jitter_x, CENTER.y() + bob)

    # "Purring" (mouse hovering), "curious" (a new program was just
    # launched -- v1.6), and "focused" (a test/build process running) are
    # all standalone reactions layered independently of git mood. Sulking
    # still wins over all three -- a cat mid-sulk doesn't warm up just
    # because the cursor is over it, something new opened, or a test
    # happens to be running. Among the three: a live hover is the most
    # immediate, direct signal (a hand on the cat right now), so it wins
    # over both of the other two, matching the existing hover-vs-focused
    # precedent from v1.5. Between curious and focused specifically: noticing
    # a brand new program appear is a discrete, momentary event (it
    # self-clears after ~2s, see window.py), while focused is a passive,
    # potentially long-running "something is happening in the background"
    # state -- a fresh, surprising thing happening right now reads as more
    # attention-grabbing than continuing to watch an already-running test,
    # so curious wins over focused whenever both are true at once. Verified
    # concretely (not just reasoned about) via a pixel-diff in this
    # feature's own dev-notes section: curious+focused renders identically
    # to curious-alone, and differs from focused-alone. (`view_mode == "pet"`
    # isn't threaded through as its own parameter here -- `window.py`'s
    # `paintEvent` already returns early without calling `paint_kitten` at
    # all while the inbox view is showing, so it's already guaranteed true
    # by the time this function runs.)
    #
    # v1.8: AWAY (real system-wide keyboard/mouse idle, distinct from the
    # git-driven IDLE mood) sits above *all* of the above, as a full
    # override rather than another layer -- the whole point of this state
    # is "nobody is here to see any of this," so it always wins.
    show_away = away
    show_purr = hovering and turn_stage is None and not show_away
    show_curious = curious and turn_stage is None and not show_purr and not show_away
    show_focused = (
        focused
        and turn_stage is None
        and not show_purr
        and not show_curious
        and not show_away
    )

    _draw_shadow(painter, center)

    frames, frame_seconds = _select_cat_frames(
        show_away, turn_stage, show_purr, show_curious, show_focused, mood
    )
    frame = frames[pixelart.frame_index(t, len(frames), frame_seconds)]
    image = pixelart.render_frame(frame, _cat_palette(night))
    pixelart.draw_pixel_image(painter, image, _cat_sprite_rect(center))

    if show_away:
        # A bigger, slower-drifting "zzz" than the regular IDLE mood
        # overlay -- reused (not reinvented) via the `deep` flag, played
        # unconditionally regardless of the git-driven mood underneath.
        _draw_zzz(painter, center, t, deep=True)
    elif turn_stage is None and not show_purr and not show_curious and not show_focused:
        # The plain "just showing mood" case -- the only one that also
        # shows a mood overlay (zzz/heart/exclaim), exactly as before.
        urgent = badge in (Badge.LOW_BATTERY, Badge.CRITICAL_BATTERY)
        _draw_mood_overlay(painter, center, mood, t, urgent=urgent)

    if accessory is not None:
        _draw_accessory(painter, center, accessory, t)

    if badge is not None and badge != Badge.NONE:
        _draw_status_badge(painter, center, badge, t)

    if streak >= 3:
        _draw_streak_icon(painter, center, streak, t)

    if nudge_text and nudge_opacity > 0.0:
        _draw_nudge_wave(painter, center, t)
        _draw_speech_bubble(
            painter,
            center,
            nudge_text,
            nudge_opacity,
            t=t,
            elapsed=nudge_elapsed,
            alert=nudge_alert,
            canvas_half_width=canvas_half_width,
        )

    # The high-five doesn't change the face/mood at all -- it's purely an
    # additive raised-paw overlay, drawn last (on top of everything else),
    # so it never has to compete with sulking/purr/focused precedence.
    if high_five:
        _draw_high_five_paw(painter, center, t)

    painter.restore()


def _draw_shadow(painter: QPainter, center: QPointF) -> None:
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(SHADOW_COLOR)
    shadow_rect = QRectF(0, 0, BODY_RX * 2.1, 10.0)
    shadow_rect.moveCenter(QPointF(center.x(), center.y() + BODY_RY + 8))
    painter.drawEllipse(shadow_rect)
    painter.restore()


# -- small chrome: badges, streak icons, seasonal accessories, mood-overlay
# icons, and the paw overlays ------------------------------------------------
# A smaller 16x16 grid -- literally reusing the cat's own 32x32-grid scale
# for a ~12-canvas-unit icon would either vanish into 1-2px slivers or force
# a huge outline; a dedicated smaller grid keeps these legible, the same
# "these can't take the main character's own proportions literally" lesson
# v1.15's own Part 4 already learned for its outline width, applied here to
# grid resolution instead. `F` is a *dynamic* "state fill" character,
# resolved to an actual color at paint time (a badge's own color/alpha
# pulse, a streak tier's gray/gold, ...) rather than baked into the grid --
# the same idiom `_cat_palette`'s night-tint swap already uses for `B`.

_CHROME_GRID_SIZE = 16

_F_badge_critical_0 = (
    "................",
    "................",
    "................",
    "................",
    ".OOOOOOOOOOOO...",
    ".OWWWWWWWWWWO...",
    ".OWFFFFWWWWWOOO.",
    ".OWFFFFWWWWWOOO.",
    ".OWFFFFWWWWWOOO.",
    ".OWFFFFWWWWWOOO.",
    ".OWWWWWWWWWWO...",
    ".OOOOOOOOOOOO...",
    "................",
    "................",
    "................",
    "................",
)
_F_badge_low_0 = (
    "................",
    "................",
    "................",
    "................",
    ".OOOOOOOOOOOO...",
    ".OWWWWWWWWWWO...",
    ".OWFFFFFFFWWOOO.",
    ".OWFFFFFFFWWOOO.",
    ".OWFFFFFFFWWOOO.",
    ".OWFFFFFFFWWOOO.",
    ".OWWWWWWWWWWO...",
    ".OOOOOOOOOOOO...",
    "................",
    "................",
    "................",
    "................",
)
_F_badge_charging_0 = (
    ".........O......",
    "........OF......",
    ".......OFF......",
    "......OFFF......",
    ".....OFFFF......",
    "....OFFFFFFFFFOO",
    "....FFFFFFFFFOOO",
    "...FFFFFFFFFFOO.",
    "..FFFFFFFFFFOO..",
    ".FFFFFFFFFFOO...",
    "OOOOOOOFFFOO....",
    "......OFFOO.....",
    "......OFOO......",
    "......OOO.......",
    "......OO........",
    "......O.........",
)
_F_badge_sweat_0 = (
    "........OOO.....",
    "......OOOOOOO...",
    "......OFFFFOO...",
    "....OOFFFFFFFOO.",
    "....OFFFFFFFFFO.",
    "...OOFFFFFFFFFO.",
    "....OOFFFFFFFFO.",
    ".....OFFFFFFFFOO",
    "......OFFFFFFFFO",
    ".......OOFFFFOO.",
    "........OOOOOO..",
    "..........OOO...",
    "................",
    "................",
    "................",
    "................",
)
_F_badge_disk_0 = (
    "................",
    "......O.........",
    "...OOOWOOO......",
    "..OWWWWWWWO.....",
    ".OWWWWWWWWWO....",
    ".OWWWWOWWWWO....",
    ".OWWWOOOWWWO....",
    "OWWWOOOOOWWWO...",
    ".OWWWOOOWWWO....",
    ".OWWWWOWWWWOOO..",
    ".OWWWWWWWWOOOO..",
    "..OWWWWWOOFOOO..",
    "...OOOWOOOFOOO..",
    "......O...OFFO..",
    "............OO..",
    "................",
)


def _draw_chrome_icon(
    painter: QPainter, pos: QPointF, frame: pixelart.Frame, palette: pixelart.Palette, px: float
) -> None:
    size = _CHROME_GRID_SIZE * px
    rect = QRectF(0, 0, size, size)
    rect.moveCenter(pos)
    image = pixelart.render_frame(frame, palette)
    pixelart.draw_pixel_image(painter, image, rect)


_BADGE_POS_OFFSET = QPointF(-BODY_RX * 0.85, -BODY_RY * 1.15)
_BADGE_PX = 1.4


def _draw_status_badge(painter: QPainter, center: QPointF, badge: Badge, t: float) -> None:
    pos = QPointF(center.x() + _BADGE_POS_OFFSET.x(), center.y() + _BADGE_POS_OFFSET.y())

    if badge == Badge.CRITICAL_BATTERY:
        _draw_battery_icon(painter, pos, QColor("#E53935"), pulse_speed=6.0, t=t, critical=True)
    elif badge == Badge.LOW_BATTERY:
        _draw_battery_icon(painter, pos, QColor("#FB8C00"), pulse_speed=1.6, t=t, critical=False)
    elif badge == Badge.CHARGING:
        palette = {"O": OUTLINE_COLOR.name(), "F": "#FDD835"}
        _draw_chrome_icon(painter, pos, _F_badge_charging_0, palette, _BADGE_PX)
    elif badge == Badge.HIGH_RESOURCE:
        bob = 1.2 * math.sin(t * 3.0)
        palette = {"O": OUTLINE_COLOR.name(), "F": "#4FC3F7"}
        _draw_chrome_icon(
            painter, QPointF(pos.x(), pos.y() + bob), _F_badge_sweat_0, palette, _BADGE_PX
        )
    elif badge == Badge.LOW_DISK:
        palette = {"O": OUTLINE_COLOR.name(), "W": "#B0BEC5", "F": "#FFB300"}
        _draw_chrome_icon(painter, pos, _F_badge_disk_0, palette, _BADGE_PX)


def _draw_battery_icon(
    painter: QPainter, pos: QPointF, color: QColor, pulse_speed: float, t: float, critical: bool
) -> None:
    # Alpha is rounded to 2 decimal places before it enters the palette --
    # otherwise this continuously-varying pulse would mint a brand-new
    # cached QImage on essentially every frame (see pixelart.py's own note
    # on why callers with a continuous value need to do this).
    alpha = round(0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * pulse_speed)), 2)
    fill = QColor(color)
    fill.setAlphaF(alpha)
    frame = _F_badge_critical_0 if critical else _F_badge_low_0
    palette = {"O": OUTLINE_COLOR.name(), "W": WHITE.name(), "F": fill.name(QColor.HexArgb)}
    _draw_chrome_icon(painter, pos, frame, palette, _BADGE_PX)


# -- commit streak ---------------------------------------------------------

_STREAK_POS_OFFSET = QPointF(BODY_RX * 0.85, -BODY_RY * 1.15)

_F_streak_star_0 = (
    "................",
    "........O.......",
    ".......OOO......",
    ".......OFO......",
    ".......FFF......",
    "......OFFFO.....",
    "..OFFFFFFFFFFFO.",
    "...OOFFFFFFFOO..",
    ".....OFFFFFO....",
    ".....OFFFFFO....",
    ".....FFFOFFF....",
    "....OFFO.OFFO...",
    "....OOO...OOO...",
    "....O.......O...",
    "................",
    "................",
)
_F_streak_crown_0 = (
    "................",
    ".......O....O...",
    ".O....OOO..OOO.O",
    ".OO...OFO..OFO.O",
    ".OOF.OOFF..FFF.O",
    ".OOFFOFFFOOFFFOO",
    ".OOFFOFFFFFFFFFO",
    ".OOFFFFFFFFFFFOO",
    ".OOFFFFFFFFFFFOO",
    ".OOFFFFFFFFFFFOO",
    ".OOFFFFFFFFFFFOO",
    ".OOFFFFFFFFFFFOO",
    ".OOFFFFFFFFFFFOO",
    ".OOOOOOOOOOOOOOO",
    "................",
    "................",
)


def _draw_streak_icon(painter: QPainter, center: QPointF, streak: int, t: float) -> None:
    pos = QPointF(center.x() + _STREAK_POS_OFFSET.x(), center.y() + _STREAK_POS_OFFSET.y())
    if streak >= 30:
        palette = {"O": OUTLINE_COLOR.name(), "F": "#FFD700"}
        _draw_chrome_icon(painter, pos, _F_streak_crown_0, palette, px=1.3)
        return
    # A gentle brightness "twinkle" -- v1.15/pre-v1.16 pulsed the star's own
    # *radius* continuously, but continuously rescaling a nearest-neighbor
    # pixel image would re-blur its edges every frame; pulsing alpha instead
    # keeps every frame genuinely crisp while still reading as a twinkle.
    twinkle = round(min(1.0, 0.7 + 0.15 * (1.0 + math.sin(t * 3.0))), 2)
    tier_color = QColor("#FFD700") if streak >= 7 else QColor("#B0BEC5")
    tier_color.setAlphaF(twinkle)
    palette = {"O": OUTLINE_COLOR.name(), "F": tier_color.name(QColor.HexArgb)}
    _draw_chrome_icon(painter, pos, _F_streak_star_0, palette, px=1.5 if streak >= 7 else 1.1)


# -- particles --------------------------------------------------------------
# Generic small fading dots (drag-trail sparkles, the shooting star) --
# unchanged from v1.15: still simple flat dots, not "the character's own
# drawn frame" this round is about, and the spec explicitly leaves a
# particle's continuous drift/fade alone.

_PARTICLE_COLOR = QColor("#FFD54F")


def draw_particles(painter: QPainter, positions: list[tuple[float, float, float]]) -> None:
    if not positions:
        return
    painter.save()
    painter.setPen(Qt.NoPen)
    for x, y, opacity in positions:
        color = QColor(_PARTICLE_COLOR)
        color.setAlphaF(max(0.0, min(1.0, opacity)))
        painter.setBrush(color)
        radius = 1.5 + 1.5 * opacity
        painter.drawEllipse(QPointF(x, y), radius, radius)
    painter.restore()


# -- mood overlays: zzz / heart / exclaim -----------------------------------


def _draw_mood_overlay(
    painter: QPainter, center: QPointF, mood: Mood, t: float, urgent: bool = False
) -> None:
    if mood == Mood.IDLE:
        _draw_zzz(painter, center, t)
    elif mood == Mood.HAPPY:
        _draw_heart(painter, center, t)
    else:
        _draw_exclaim_bubble(painter, center, t, urgent=urgent)


def _draw_zzz(painter: QPainter, center: QPointF, t: float, deep: bool = False) -> None:
    # Left as plain drawn text rather than a pixel-grid glyph -- there's no
    # small bitmap font in this codebase to draw "z" from a grid without
    # inventing one from scratch, well out of proportion to what three
    # drifting letters are worth. Antialiasing is turned off locally so it
    # at least reads a little more "blocky retro" than a fully smoothed
    # font would, without pretending it's genuine pixel art.
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, False)
    font = QFont("Comic Sans MS", 10)
    font.setItalic(True)
    painter.setFont(font)

    drift_speed = 0.28 if deep else 0.5
    rise_amount = 22.0 if deep else 16.0
    size_bonus = 3 if deep else 0
    top_y_factor = 1.05 if deep else 1.35
    top = QPointF(center.x() + BODY_RX * 0.5, center.y() - BODY_RY * top_y_factor)
    letters = "zzz"
    for i, ch in enumerate(letters):
        phase = (t * drift_speed + i * 0.33) % 1.0
        rise = phase * rise_amount
        alpha = int(220 * (1.0 - phase))
        size = 7 + i * 2 + size_bonus
        f = QFont(font)
        f.setPointSizeF(size)
        painter.setFont(f)
        color = QColor(ZZZ_COLOR)
        color.setAlpha(max(0, alpha))
        painter.setPen(color)
        pos = QPointF(top.x() + i * 5, top.y() - rise)
        painter.drawText(pos, ch)
    painter.restore()


_F_heart_0 = (
    "................",
    "................",
    ".....O.....O....",
    "...OOPOO.OOPOO..",
    "..OPPPPPOPPPPPO.",
    "..OPPPPPOPPPPPO.",
    ".OPPPPPPPPPPPPPO",
    "..OPPPPPPPPPPPO.",
    "..OPPPPPPPPPPPO.",
    "...OOPPPPPPPOO..",
    "....OOPPPPPOO...",
    ".....OOPPPOO....",
    "......OOPOO.....",
    ".......OOO......",
    "........O.......",
    "................",
)
_HEART_PALETTE = {"O": OUTLINE_COLOR.name(), "P": "#F06292"}


def _draw_heart(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    pulse = 1.0 + 0.12 * math.sin(t * 5.0)
    hx = center.x()
    hy = center.y() - BODY_RY * 1.55
    _draw_chrome_icon(painter, QPointF(hx, hy), _F_heart_0, _HEART_PALETTE, px=1.3 * pulse)

    for i in range(3):
        sparkle_phase = (t * 0.8 + i * 0.33) % 1.0
        sx = hx + (i - 1) * 16
        sy = hy - 14 - sparkle_phase * 14
        alpha = int(255 * (1.0 - sparkle_phase))
        color = QColor("#FFD54F")
        color.setAlpha(max(0, alpha))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(sx, sy), 2.2, 2.2)
    painter.restore()


_F_exclaim_0 = (
    "................",
    "........O.......",
    ".....OOOWOOO....",
    "....OWWWWWWWO...",
    "...OWWWOOOWWWO..",
    "..OWWWWOOOWWWWO.",
    "..OWWWWOOOWWWWO.",
    "..OWWWWOOOWWWWO.",
    ".OWWWWWOOOWWWWWO",
    "..OWWWWOOOWWWWO.",
    "..OWWWWWWWWWWWO.",
    "..OWWWWOOOWWWWO.",
    "...OWWWOOOWWWO..",
    "....OWWWWWWWO...",
    ".....OOOWOOO....",
    "........O.......",
)
_F_exclaim_urgent_0 = (
    "................",
    "........O.......",
    ".....OOOWOOO....",
    "....OWWWWWWWO...",
    "...OWWOOWWOOWO..",
    "..OWWWOOWWOOWWO.",
    "..OWWWOOWWOOWWO.",
    "..OWWWOOWWOOWWO.",
    ".OWWWWOOWWOOWWWO",
    "..OWWWOOWWOOWWO.",
    "..OWWWWWWWWWWWO.",
    "..OWWWOOWWOOWWO.",
    "...OWWOOWWOOWO..",
    "....OWWWWWWWO...",
    ".....OOOWOOO....",
    "................",
)
_EXCLAIM_PALETTE = {"O": OUTLINE_COLOR.name(), "W": WHITE.name()}


def _draw_exclaim_bubble(
    painter: QPainter, center: QPointF, t: float, urgent: bool = False
) -> None:
    bounce = 2.0 * abs(math.sin(t * 3.0))
    bx = center.x() + BODY_RX * 0.55
    by = center.y() - BODY_RY * 1.45 - bounce
    frame = _F_exclaim_urgent_0 if urgent else _F_exclaim_0
    _draw_chrome_icon(painter, QPointF(bx, by), frame, _EXCLAIM_PALETTE, px=1.3)


# -- seasonal accessories -----------------------------------------------------

_ACCESSORY_POS = QPointF(0.0, -BODY_RY * 1.55)

_F_acc_witch_0 = (
    "................",
    "................",
    "......OO........",
    "......OO........",
    "......HH........",
    ".....OHHO.......",
    ".....OHHO.......",
    ".....HHHH.......",
    "....OHHHHO......",
    "....OHHHHO......",
    "...VVVVVVVVV....",
    "...VVVVVVVVV....",
    "OHHHHHHHHHHHHHHO",
    "OHHHHHHHHHHHHHHO",
    "OOOOOOOOOOOOOOOO",
    "................",
)
_F_acc_pomegranate_0 = (
    ".......OO.......",
    "......OOOO......",
    ".....OOGGOO.....",
    ".....OGGGGOO....",
    "....ORRRRRRRO...",
    "...ORRRRRRRRRO..",
    "...ORRRRRRRRRO..",
    "...ORRRRRRRRRO..",
    "..ORRRRRRRRRRRO.",
    "...ORRRRRRRRRO..",
    "...ORRRRRRRRRO..",
    "...ORRRRRRRRRO..",
    "....ORRRRRRRO...",
    ".....OOOROOO....",
    "........O.......",
    "................",
)
_F_acc_party_0 = (
    ".......OWO......",
    "......OWWWO.....",
    ".......OWO......",
    ".......TO.......",
    "......OTTO......",
    "......TTTT......",
    ".....OTTTTO.....",
    "....OTTTTTTO....",
    "....OTTTTTTO....",
    "...OTTTTTTTTO...",
    "...OTTTTTTTTO...",
    "..OTTTTTTTTTTO..",
    "..OOOOOOOOOOOO..",
    ".OOOOOOOOOOOOOO.",
    "................",
    "................",
)
_ACCESSORY_FRAMES = {
    "halloween": _F_acc_witch_0,
    "yalda": _F_acc_pomegranate_0,
    "birthday": _F_acc_party_0,
}
_ACCESSORY_PALETTES: dict[str, pixelart.Palette] = {
    "halloween": {"O": OUTLINE_COLOR.name(), "H": "#2B2B33", "V": "#7B4FA0"},
    "yalda": {"O": OUTLINE_COLOR.name(), "R": "#B32B3A", "G": "#5C8A4A"},
    "birthday": {"O": OUTLINE_COLOR.name(), "T": "#42A5F5", "W": WHITE.name()},
}


def _draw_accessory(painter: QPainter, center: QPointF, accessory: str, t: float) -> None:
    frame = _ACCESSORY_FRAMES.get(accessory)
    if frame is None:
        return
    pos = QPointF(center.x() + _ACCESSORY_POS.x(), center.y() + _ACCESSORY_POS.y())
    _draw_chrome_icon(painter, pos, frame, _ACCESSORY_PALETTES[accessory], px=1.7)


# -- distraction nudge / high five paws --------------------------------------
# Both keep their pre-v1.16 continuous *position* animation (a bob, a
# wobble) exactly as before -- only the paw's own drawn shape is now a
# pixel-art image instead of a smooth circle + dot toes.

_F_paw_0 = (
    "................",
    "................",
    "...OCO.OCO.OCO..",
    "...CCC.CCC.CCC..",
    "...OCOOOCOOOCO..",
    "....OCCCCCCCO...",
    "...OCCCCCCCCCO..",
    "...OCCCCCCCCCO..",
    "...OCCCCCCCCCO..",
    "..OCCCCCCCCCCCO.",
    "...OCCCCCCCCCO..",
    "...OCCCCCCCCCO..",
    "...OCCCCCCCCCO..",
    "....OCCCCCCCO...",
    ".....OOOCOOO....",
    "........O.......",
)
_PAW_PALETTE = {"O": OUTLINE_COLOR.name(), "C": SECONDARY_FILL_COLOR.name()}


def _draw_nudge_wave(painter: QPainter, center: QPointF, t: float) -> None:
    swing = math.sin(t * 8.0)
    paw_x = center.x() + BODY_RX * 0.95
    paw_y = center.y() + BODY_RY * 0.1 - 8.0 * max(0.0, swing)
    _draw_chrome_icon(painter, QPointF(paw_x, paw_y), _F_paw_0, _PAW_PALETTE, px=0.85)


def _draw_high_five_paw(painter: QPainter, center: QPointF, t: float) -> None:
    wobble = 1.5 * math.sin(t * 10.0)
    paw_x = center.x() + BODY_RX * 0.85 + wobble
    paw_y = center.y() - BODY_RY * 0.75
    _draw_chrome_icon(painter, QPointF(paw_x, paw_y), _F_paw_0, _PAW_PALETTE, px=1.0)


# -- distraction/reminder speech bubble --------------------------------------
# Unchanged from v1.14/v1.15 -- the bubble card itself is theme.py-era UI
# chrome (a themed rounded rect, per v1.14's own dev-notes entry), not "the
# cat/mouse sprite art" this round's spec scopes itself to. Only the small
# paw overlay drawn alongside it (above) changed this round.

_NUDGE_BUBBLE_BOTTOM_OFFSET = BODY_RY * 1.05

_ALERT_FILL_COLOR = theme.WARNING_FILL
_ALERT_BORDER_COLOR = theme.WARNING_BORDER
_ALERT_ICON_RESERVE = 20.0
_ALERT_POP_SECONDS = 0.22

_BUBBLE_FILL_COLOR = theme.SURFACE_CARD
_BUBBLE_BORDER_COLOR = theme.BORDER
_BUBBLE_TEXT_COLOR = theme.TEXT_PRIMARY
_BUBBLE_PADDING_X = float(theme.SPACING_SM)
_BUBBLE_PADDING_Y = float(theme.SPACING_XS)


def nudge_bubble_size(text: str, alert: bool) -> tuple[float, float]:
    """The natural (unclamped) single-line bubble size, in canvas units,
    for `text`/`alert` -- the single source of truth for this geometry,
    shared between `_draw_speech_bubble`'s actual drawing below and
    `KittenWindow._grow_for_nudge` (window.py), which needs to know how
    wide the *physical window itself* must temporarily grow to fit a long
    reply without clipping it."""
    font = QFont(theme.FONT_FAMILY, 9, QFont.Bold if alert else QFont.Normal)
    metrics = QFontMetricsF(font)
    padding_x, padding_y = _BUBBLE_PADDING_X, _BUBBLE_PADDING_Y
    icon_reserve = _ALERT_ICON_RESERVE if alert else 0.0
    tw = metrics.horizontalAdvance(text)
    th = metrics.height()
    return tw + padding_x * 2 + icon_reserve, th + padding_y * 2


def _draw_speech_bubble(
    painter: QPainter,
    center: QPointF,
    text: str,
    opacity: float,
    t: float = 0.0,
    elapsed: float = 0.0,
    alert: bool = False,
    canvas_half_width: float = CANVAS / 2,
) -> None:
    painter.save()
    painter.setOpacity(max(0.0, min(1.0, opacity)))

    font = QFont(theme.FONT_FAMILY, 9, QFont.Bold if alert else QFont.Normal)
    painter.setFont(font)
    padding_x = _BUBBLE_PADDING_X
    icon_reserve = _ALERT_ICON_RESERVE if alert else 0.0
    bubble_w, bubble_h = nudge_bubble_size(text, alert)

    bubble = QRectF(0, 0, bubble_w, bubble_h)
    bubble_bottom = center.y() - _NUDGE_BUBBLE_BOTTOM_OFFSET
    bubble.moveCenter(QPointF(center.x(), bubble_bottom - bubble.height() / 2))
    left_bound = CANVAS / 2 - canvas_half_width + 2
    right_bound = CANVAS / 2 + canvas_half_width - 2
    if bubble.left() < left_bound:
        bubble.moveLeft(left_bound)
    if bubble.right() > right_bound:
        bubble.moveRight(right_bound)
    if bubble.top() < 2:
        bubble.moveTop(2)

    if alert and elapsed < _ALERT_POP_SECONDS:
        scale = 0.6 + 0.4 * max(0.0, elapsed / _ALERT_POP_SECONDS)
        painter.translate(bubble.center())
        painter.scale(scale, scale)
        painter.translate(-bubble.center())

    fill = _ALERT_FILL_COLOR if alert else _BUBBLE_FILL_COLOR
    border = _ALERT_BORDER_COLOR if alert else _BUBBLE_BORDER_COLOR
    pen = _outline_pen(2.2 if alert else 1.2)
    pen.setColor(border)
    painter.setPen(pen)
    painter.setBrush(fill)
    painter.drawRoundedRect(bubble, 6.0, 6.0)

    tail = QPainterPath(QPointF(center.x() - 4, bubble.bottom() - 1))
    tail.lineTo(QPointF(center.x() + 4, bubble.bottom() - 1))
    tail.lineTo(QPointF(center.x(), bubble.bottom() + 7))
    tail.closeSubpath()
    painter.setBrush(fill)
    painter.drawPath(tail)

    if alert:
        icon_pos = QPointF(bubble.left() + padding_x + 7.0, bubble.center().y())
        _draw_alarm_icon(painter, icon_pos, t)
        text_rect = QRectF(
            bubble.left() + padding_x + icon_reserve,
            bubble.top(),
            bubble.width() - padding_x * 2 - icon_reserve,
            bubble.height(),
        )
        painter.setPen(_BUBBLE_TEXT_COLOR)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
    else:
        painter.setPen(_BUBBLE_TEXT_COLOR)
        painter.drawText(bubble, Qt.AlignCenter, text)
    painter.restore()


def _draw_alarm_icon(painter: QPainter, pos: QPointF, t: float) -> None:
    """A small alarm-clock glyph shown at the left of an alert bubble --
    unchanged v1.14-era UI chrome, out of this round's scope."""
    painter.save()
    ring = 6.0 * math.sin(t * 9.0)
    painter.translate(pos)
    painter.rotate(ring)
    radius = 6.5
    painter.setPen(_outline_pen(1.2))
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    painter.drawLine(QPointF(-4.6, -4.6), QPointF(-7.0, -7.4))
    painter.drawLine(QPointF(4.6, -4.6), QPointF(7.0, -7.4))
    hand_pen = _outline_pen(1.3)
    hand_pen.setColor(_ALERT_BORDER_COLOR)
    painter.setPen(hand_pen)
    painter.drawLine(QPointF(0, 0), QPointF(0, -3.6))
    painter.drawLine(QPointF(0, 0), QPointF(2.8, 1.4))
    painter.restore()


# -- mouse (v1.7 chase minigame) --------------------------------------------
# Its own small logical canvas (mirroring the cat's own canvas-plus-scale
# transform pattern) and its own 16x16 pixel grid -- no mood/state of its
# own, just a 2-frame breathing cycle per the spec.

MOUSE_CANVAS = 64.0
_MOUSE_CENTER = QPointF(MOUSE_CANVAS / 2, MOUSE_CANVAS / 2 + 4)

_F_mouse_0 = (
    "................",
    "..........O.....",
    "..OC......CO....",
    "..CCO....OCCO...",
    ".OOOOO..OOOOOO..",
    ".....OOOBOOO....",
    "....OBBBBBBBO...",
    "...OBBBBBBBBBO..",
    "...OBBOBBBBOBOO.",
    "..OBBBBBBBBBBBOO",
    "...OBBBBBBBBBOBO",
    "...OBBBBBBBBBOBO",
    "....OBBBBBBBOOOB",
    ".....OOOBOOO..OO",
    "........O.......",
    "................",
)
_F_mouse_1 = (
    "................",
    "..........O.....",
    "..OC......CO....",
    "..CCO...OOCCO...",
    ".OOOOOOOBOOOOO..",
    "....OBBBBBBBO...",
    "...OBBBBBBBBBO..",
    "...OBBOBBBBOBO..",
    "..OBBBBBBBBBBBO.",
    "...OBBBBBBBBBOBO",
    "...OBBBBBBBBBOBO",
    "....OBBBBBBBOOBO",
    ".....OOOBOOO.OOB",
    "........O.....OO",
    "................",
    "................",
)
_MOUSE_FRAMES: tuple[pixelart.Frame, ...] = (_F_mouse_0, _F_mouse_1)
_MOUSE_FRAME_SECONDS = 0.9
# A flat, cool slate gray -- still clearly "not the cat" at a glance, with
# the same warm SECONDARY_FILL_COLOR the cat's own inner ears/paw pads use
# for its ears, so the two sprites read as one shared palette family.
_MOUSE_BODY_COLOR = QColor("#AEB4BD")
_MOUSE_PALETTE: pixelart.Palette = {
    "O": OUTLINE_COLOR.name(),
    "B": _MOUSE_BODY_COLOR.name(),
    "C": SECONDARY_FILL_COLOR.name(),
}
_MOUSE_GRID_SIZE = 16
_MOUSE_GRID_PX = 3.0
_MOUSE_ANCHOR_COL = 8.0
_MOUSE_ANCHOR_ROW = 9.0


def paint_mouse(painter: QPainter, rect: QRectF, t: float) -> None:
    """Draws the mouse (rodent) sprite for the v1.7 chase minigame -- a
    single 2-frame breathing pose, no mood/interaction states of its own,
    exactly as before; only the drawing technique changed this round."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    scale = min(rect.width(), rect.height()) / MOUSE_CANVAS
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.translate(-MOUSE_CANVAS / 2, -MOUSE_CANVAS / 2)

    center = _MOUSE_CENTER
    size = _MOUSE_GRID_SIZE * _MOUSE_GRID_PX
    target = QRectF(
        center.x() - _MOUSE_ANCHOR_COL * _MOUSE_GRID_PX,
        center.y() - _MOUSE_ANCHOR_ROW * _MOUSE_GRID_PX,
        size,
        size,
    )
    frame = _MOUSE_FRAMES[pixelart.frame_index(t, len(_MOUSE_FRAMES), _MOUSE_FRAME_SECONDS)]
    image = pixelart.render_frame(frame, _MOUSE_PALETTE)
    pixelart.draw_pixel_image(painter, image, target)

    painter.restore()
