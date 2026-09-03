"""Drawing code for the kitten and mouse sprites -- `paint_kitten`/
`paint_mouse` are pure with respect to Qt widget state: give either one a
painter, a target rect, the relevant mood/pose flags, and a monotonically
increasing time in seconds, and it draws one animated frame. No external
art assets or files; everything lives in this module.

## v1.17 -- a bold-outline calico chibi redesign (Phase 5), replacing v1.16

Per `GITTEN_V1_17_SPEC.md`, this round fully replaces v1.16's pixel-grid
rendering (`pixelart.py`, now unused and deleted) with smooth
`QPainterPath` vector shapes again -- closer to v1.15's own *technique* --
but restyled: a much thicker, bolder uniform outline; flat two-tone
"calico" patch coloring (a white/cream base plus `theme.ACCENT` as an
asymmetric patch, not a single solid body color); and a real chibi body
(a large head, a small simple torso + two paws beneath it) instead of
either recent redesign's single body-sized silhouette. Continuous smooth
motion (breathing/swaying/blinking via sine waves driven by `t`) replaces
v1.16's discrete frame-swapping -- a deliberate reversal back to v1.15's
own animation model, stated explicitly per the spec's own framing, not a
silent regression. Every pose's precedence order and animation timing that
isn't about the character's own drawn shape (away > sulk > purr > curious
> focused > plain mood; bob/jitter/drift/pulse speeds) is unchanged from
every prior round.

An entirely original character, designed from scratch for this project --
inspired by the general pixel-pet/calico-mascot aesthetic broadly (bold
outlines, patchy two-tone coloring, chibi proportions, simple dot eyes),
not copied from or referencing any specific existing character, creator,
or franchise, per the spec's explicit originality note.

See `DEVELOPMENT_NOTES.md`'s v1.17 entry for the part-by-part build order
and the live-screenshot verification for each part.
"""

from __future__ import annotations

import math
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)

from gitten import theme
from gitten.mood import Mood
from gitten.status_badge import Badge

# -- palette ------------------------------------------------------------
# The "calico" two-tone scheme: a light base fur color plus theme.ACCENT as
# an asymmetric patch color, rather than v1.15/v1.16's single solid body
# tone. `theme.SURFACE_CARD` (plain white) is reused verbatim as the base
# fur -- theme.py's own audited light surface tone, per the spec's "audit
# before inventing" instruction, rather than a new one-off hex.
FUR_COLOR = theme.SURFACE_CARD
PATCH_COLOR = theme.ACCENT
# Still used for the nudge-wave/high-five paw pads and the mouse's own
# ears -- theme.py's "accent lightened toward white" variant, unchanged
# from v1.15/v1.16's own reuse of it.
SECONDARY_FILL_COLOR = theme.ACCENT_SOFT
# The one outline/ink color used throughout every shape below.
OUTLINE_COLOR = theme.TEXT_PRIMARY
WHITE = theme.SURFACE_CARD
# Soft blush cheeks reuse the app's existing heart-icon pink (below) at low
# alpha, rather than inventing a new pink hue family just for this.
BLUSH_COLOR = QColor("#F06292")
SHADOW_COLOR = QColor(0, 0, 0, 60)
ZZZ_COLOR = QColor(120, 120, 128, 220)

CANVAS = 128.0
# The head's own center -- bob/jitter/drag animate this point, same as
# every prior round's single "center". Kept a touch higher than v1.15/
# v1.16's (70) since a real chibi torso now sits below it rather than the
# head itself occupying the lower half of the canvas.
CENTER = QPointF(CANVAS / 2, 50.0)
# The head ellipse's own radii -- kept under the legacy `BODY_RX`/`BODY_RY`
# names since every overlay (badge/streak/accessory/bubble/paw-wave)
# already positions itself relative to these, exactly as in every prior
# round, where the head was always the dominant silhouette these offsets
# were tuned against.
BODY_RX, BODY_RY = 34.0, 32.0

# v1.17: much thicker and bolder than v1.15's 3.2 -- a defining trait of
# this style, not a subtle bump -- and, per that same round's discipline,
# held uniform across body/torso/paws/ears/tail rather than varied per
# element (small chrome -- badges/streak/accessories -- gets its own
# smaller, still-uniform width below, the same two-tier approach v1.15
# already established).
_OUTLINE_PEN_WIDTH = 4.6
# A visibly thinner pen for fine face detail (whisker marks, the mouth,
# closed-eye curves) that would be swallowed by the full body/head outline
# weight at this small a scale.
_DETAIL_PEN_WIDTH = 2.4


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
    from v1.15/v1.16 -- still how night-mode tints a color."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * factor),
        round(a.green() + (b.green() - a.green()) * factor),
        round(a.blue() + (b.blue() - a.blue()) * factor),
    )


def _fur_color(night: bool) -> QColor:
    return _blend_color(FUR_COLOR, _MOONLIT_BASE, _NIGHT_BLEND_FACTOR) if night else FUR_COLOR


def _patch_color(night: bool) -> QColor:
    return _blend_color(PATCH_COLOR, _MOONLIT_BASE, _NIGHT_BLEND_FACTOR) if night else PATCH_COLOR


# -- chibi torso + paw layout -------------------------------------------
# A small, simple body beneath the head -- chibi proportions, not a return
# to v1's more evenly-proportioned body. Two layouts: the normal sitting
# posture, and a lower/flatter/tucked-in one for the AWAY deep-sleep pose
# (see `_draw_torso`/`_draw_paws` below) -- leaning into the pose's
# curled-up chibi quality rather than just swapping the face.
TORSO_RX, TORSO_RY = 20.0, 16.0
TORSO_OFFSET_Y = 42.0
TORSO_OFFSET_Y_AWAY = 28.0
TORSO_RX_AWAY = 25.0
TORSO_RY_AWAY = 12.0
PAW_RX, PAW_RY = 8.0, 6.5
PAW_DX = 13.0
PAW_DX_AWAY = 10.0


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

    # Normally rect.width() == rect.height() == the fixed window size. But
    # window.py temporarily widens the physical window (height fixed, so
    # `scale` above stays unchanged) to fit a nudge bubble too wide for the
    # plain canvas; this is how much canvas-unit half-width is actually
    # available to draw into, used only by the nudge bubble's own clamping.
    canvas_half_width = rect.width() / (2 * scale)

    # `bob` (a gentle vertical float) and `jitter_x` (the WAITING mood's
    # nervous shiver) animate the cat's *position*, continuously, exactly
    # as every prior round -- unchanged by this round's drawing-technique
    # swap.
    bob = 1.5 * math.sin(t * 2.0) if not dragging else 0.0
    jitter_x = 0.6 * math.sin(t * 14.0) if mood == Mood.WAITING and not away else 0.0
    center = QPointF(CENTER.x() + jitter_x, CENTER.y() + bob)
    breathe = 1.0 + 0.02 * math.sin(t * 2.0)
    away_breathe = 1.0 + 0.05 * math.sin(t * 0.7)
    tail_phase = math.sin(t * 1.6) * 0.5 + math.sin(t * 0.7) * 0.2

    # Same standalone-reaction precedence every round has used: away wins
    # over everything; sulking wins over purr/curious/focused; a live hover
    # wins over curious/focused; a fresh app launch wins over focused.
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

    _draw_shadow(painter, center, show_away)

    if not show_away:
        _draw_tail(painter, center, tail_phase, night=night)

    _draw_torso(painter, center, away_breathe if show_away else breathe, night=night, lying=show_away)
    _draw_paws(painter, center, show_away)

    if show_away:
        _draw_tail(painter, center, tail_phase, curled=True, night=night)
        _draw_ears(painter, center, breathe, drooping=True, t=t, night=night)
        _draw_head(painter, center, night=night)
        _draw_sleep_face(painter, center, t)
    elif show_curious:
        with _head_tilt(painter, center, _CURIOSITY_TILT_DEGREES):
            _draw_ears(painter, center, breathe, perked=True, t=t, night=night)
            _draw_head(painter, center, night=night)
            _draw_face_details(painter, center)
            _draw_curious_face(painter, center, t)
    else:
        _draw_ears(painter, center, breathe, perked=show_focused, wiggle=show_purr, t=t, night=night)
        _draw_head(painter, center, night=night)
        if turn_stage is not None:
            _draw_face_turned(painter, center, turn_stage, t)
        else:
            _draw_face_details(painter, center)
            if show_purr:
                _draw_purr_face(painter, center, t)
            elif show_focused:
                _draw_focused_face(painter, center, t)
            else:
                _draw_face(painter, center, mood, t)
                urgent = badge in (Badge.LOW_BATTERY, Badge.CRITICAL_BATTERY)
                _draw_mood_overlay(painter, center, mood, t, urgent=urgent)

    if show_away:
        # A bigger, slower-drifting "zzz" than the regular IDLE mood
        # overlay -- reused (not reinvented) via the `deep` flag, played
        # unconditionally regardless of the git-driven mood underneath.
        _draw_zzz(painter, center, t, deep=True)

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
    # additive raised-paw overlay, drawn last (on top of everything else).
    if high_five:
        _draw_high_five_paw(painter, center, t)

    painter.restore()


def _draw_shadow(painter: QPainter, center: QPointF, away: bool) -> None:
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(SHADOW_COLOR)
    offset_y = TORSO_OFFSET_Y_AWAY if away else TORSO_OFFSET_Y
    rx = (TORSO_RX_AWAY if away else TORSO_RX) * 1.6
    shadow_rect = QRectF(0, 0, rx * 2, 9.0)
    shadow_rect.moveCenter(QPointF(center.x(), center.y() + offset_y + 14))
    painter.drawEllipse(shadow_rect)
    painter.restore()


# -- tail -----------------------------------------------------------------
# The same "stroke a wider outline-colored line underneath, a narrower
# fill-colored line on top" technique v1.15 introduced for a real
# silhouette outline (not just a centerline seam) -- still the right
# technique for a smooth curved tail, just re-scaled for this round's
# smaller chibi torso.

_TAIL_WIDTH = 7.0
_TAIL_WIDTH_CURLED = 5.5
_TAIL_OUTLINE_EXTRA = 3.2


def _draw_tail(
    painter: QPainter, center: QPointF, phase: float, curled: bool = False, night: bool = False
) -> None:
    painter.save()
    torso_y = center.y() + (TORSO_OFFSET_Y_AWAY if curled else TORSO_OFFSET_Y)

    if curled:
        # Tucked into a small curled loop against the flattened lying
        # torso -- reads as "settled down to sleep" rather than alert.
        # Endpoints are kept well separated (not a tight ~9-unit loop) so
        # the RoundCap line ends don't merge into one solid blob at this
        # bolder outline width -- the same lesson v1.15's own dev notes
        # recorded for its away pose.
        width = _TAIL_WIDTH_CURLED
        base = QPointF(center.x() + TORSO_RX_AWAY * 0.85, torso_y + 2)
        c1 = QPointF(base.x() + 11, base.y() - 4)
        c2 = QPointF(base.x() + 13, base.y() - 17)
        end = QPointF(base.x() - 2, base.y() - 15)
    else:
        width = _TAIL_WIDTH
        # Rooted at the torso's own lower-back side (well inside its
        # silhouette, not right at the head/torso seam) so the visible
        # curve reads as clearly emerging from the body, not floating near
        # the busy head/torso junction -- confirmed by rendering an earlier
        # version with the root right at that seam and finding the tail
        # read as a disconnected loose hook, not an attached tail.
        base = QPointF(center.x() + TORSO_RX * 0.9, torso_y + TORSO_RY * 0.45)
        sway = 12.0 * phase
        c1 = QPointF(base.x() + 15, base.y() - 3 + sway * 0.3)
        c2 = QPointF(base.x() + 19, base.y() - 23 + sway)
        end = QPointF(base.x() + 9, base.y() - 36 + sway * 1.1)

    path = QPainterPath(base)
    path.cubicTo(c1, c2, end)

    outline = _outline_pen(width + _TAIL_OUTLINE_EXTRA)
    painter.setPen(outline)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    fill = QPen(_fur_color(night), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(fill)
    painter.drawPath(path)
    painter.restore()


# -- torso + paws -----------------------------------------------------------


def _draw_torso(
    painter: QPainter, center: QPointF, breathe: float, night: bool = False, lying: bool = False
) -> None:
    painter.save()
    rx = TORSO_RX_AWAY if lying else TORSO_RX
    ry = TORSO_RY_AWAY if lying else TORSO_RY
    offset_y = TORSO_OFFSET_Y_AWAY if lying else TORSO_OFFSET_Y
    rect = QRectF(0, 0, rx * 2, ry * 2 * breathe)
    rect.moveCenter(QPointF(center.x(), center.y() + offset_y))

    painter.setPen(_outline_pen())
    painter.setBrush(_fur_color(night))
    painter.drawEllipse(rect)
    painter.restore()


def _draw_paws(painter: QPainter, center: QPointF, away: bool) -> None:
    """Two small visible paws peeking out beneath the torso -- matching the
    head/torso's own outline weight, per the confirmed design (not a
    smaller detail-scale stroke like the whiskers/mouth)."""
    painter.save()
    offset_y = TORSO_OFFSET_Y_AWAY if away else TORSO_OFFSET_Y
    ry = TORSO_RY_AWAY if away else TORSO_RY
    dx = PAW_DX_AWAY if away else PAW_DX
    paw_y = center.y() + offset_y + ry * 0.72
    painter.setPen(_outline_pen())
    painter.setBrush(WHITE)
    for side in (-1, 1):
        rect = QRectF(0, 0, PAW_RX * 2, PAW_RY * 2)
        rect.moveCenter(QPointF(center.x() + side * dx, paw_y))
        painter.drawEllipse(rect)
    painter.restore()


# -- ears -------------------------------------------------------------------
# Asymmetric, per the confirmed design: one ear plain white (the base fur
# color), the other plain orange (theme.ACCENT) -- not a matching pair, and
# not a two-tone ear with a separate inner-ear shade, just one flat color
# each, which is what actually reads as "calico" rather than "mismatched
# highlight." The orange ear sits on the same side as the face's own orange
# patch below, so the two read as one coherent marking rather than two
# unrelated accents.

_EAR_ACCENT_SIDE = 1  # the right ear (character's own right) is orange


def _draw_ears(
    painter: QPainter,
    center: QPointF,
    breathe: float,
    perked: bool = False,
    wiggle: bool = False,
    t: float = 0.0,
    drooping: bool = False,
    night: bool = False,
) -> None:
    painter.save()
    height_scale = 1.25 if perked else (0.45 if drooping else 1.0)
    lean = 0.5 if perked else (1.7 if drooping else 1.0)
    sway = 2.2 * math.sin(t * 3.0) if wiggle else 0.0

    for side in (-1, 1):
        ex = center.x() + side * BODY_RX * 0.62
        ey = center.y() - BODY_RY * 0.78
        base_in = QPointF(ex - 13 * side, ey + 11)
        base_out = QPointF(ex + 16 * side, ey + 13)
        tip = QPointF(ex + 5 * side * lean + sway, ey - 25 * breathe * height_scale)

        path = QPainterPath(base_in)
        path.quadTo(QPointF(ex - 3 * side, ey - 12 * breathe * height_scale), tip)
        path.quadTo(QPointF(ex + 11 * side, ey - 1 * breathe * height_scale), base_out)
        path.closeSubpath()

        color = _patch_color(night) if side == _EAR_ACCENT_SIDE else _fur_color(night)
        painter.setPen(_outline_pen())
        painter.setBrush(color)
        painter.drawPath(path)
    painter.restore()


@contextmanager
def _head_tilt(painter: QPainter, center: QPointF, degrees: float):
    """Rotate everything drawn inside the block by `degrees` around
    `center`, then restore -- used to tilt just the ears+head+face (not the
    torso/tail, drawn outside this block) for the curiosity reaction."""
    painter.save()
    try:
        painter.translate(center)
        painter.rotate(degrees)
        painter.translate(-center.x(), -center.y())
        yield
    finally:
        painter.restore()


# -- head + the calico facial patch -----------------------------------------
# The confirmed technique: fill the head fully in the base fur color, then
# fill the orange patch *clipped to the head's own outline path* (so its
# outer edge always sits flush with the head silhouette, no hand-positioned
# points to get wrong and no gap/sliver of fur ever visible between them),
# then stroke the head's outline on top last so one continuous bold line
# bounds both fur colors cleanly.

_PATCH_HALF_W = 10.0
_PATCH_HALF_H = 40.0
_PATCH_ANGLE_DEGREES = 12.0


def _head_path(center: QPointF) -> QPainterPath:
    path = QPainterPath()
    rect = QRectF(0, 0, BODY_RX * 2, BODY_RY * 2)
    rect.moveCenter(center)
    path.addEllipse(rect)
    return path


def _draw_head(painter: QPainter, center: QPointF, night: bool = False) -> None:
    painter.save()
    head_path = _head_path(center)

    # 1) base fur fill, no stroke yet.
    painter.setPen(Qt.NoPen)
    painter.setBrush(_fur_color(night))
    painter.drawPath(head_path)

    # 2) the orange patch, clipped to the head's own silhouette -- drawn
    # deliberately oversized (its ellipse extends well past the head's own
    # edge on every side) so the clip -- not hand-placed points -- is what
    # guarantees the flush outer edge.
    painter.save()
    painter.setClipPath(head_path)
    patch_center = QPointF(
        center.x() + _EAR_ACCENT_SIDE * BODY_RX * 0.76, center.y() - BODY_RY * 0.06
    )
    painter.translate(patch_center)
    painter.rotate(_EAR_ACCENT_SIDE * _PATCH_ANGLE_DEGREES)
    painter.setBrush(_patch_color(night))
    painter.drawEllipse(QPointF(0, 0), _PATCH_HALF_W, _PATCH_HALF_H)
    painter.restore()

    # 3) the head's own bold outline, stroked last on top of both fills.
    painter.setPen(_outline_pen())
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(head_path)
    painter.restore()


# -- face detail: blush + whisker marks --------------------------------------
# Drawn for every front-facing state except mid-sulk (the face is turned
# away, so a floating blush/whisker mark on an unseen cheek would read as a
# mistake, not a style choice) -- the same "only shown where it makes sense"
# rule this codebase already applies to e.g. the away zzz overlay.

_BLUSH_OFFSET = QPointF(19.0, 11.0)
_BLUSH_RADIUS = 6.5
_BLUSH_ALPHA = 95

# Whisker marks on both cheeks, mirrored: orange marks over the plain white
# fur side, white marks over the orange patch side. The patch side's x-range
# is shifted further out (not a literal mirror of the white side's range)
# so the marks actually land on the patch fill rather than partway off it,
# confirmed by looking at the rendered patch's own footprint at cheek
# height before picking these numbers.
_WHISKER_Y_OFFSET = 5.0
_WHISKER_ROWS = (-4.0, 0.0, 4.0)


def _draw_face_details(painter: QPainter, center: QPointF) -> None:
    painter.save()

    # Blush.
    painter.setPen(Qt.NoPen)
    blush = QColor(BLUSH_COLOR)
    blush.setAlpha(_BLUSH_ALPHA)
    painter.setBrush(blush)
    for side in (-1, 1):
        pos = QPointF(center.x() + side * _BLUSH_OFFSET.x(), center.y() + _BLUSH_OFFSET.y())
        painter.drawEllipse(pos, _BLUSH_RADIUS, _BLUSH_RADIUS)

    # Whisker marks.
    for side in (-1, 1):
        color = FUR_COLOR if side == _EAR_ACCENT_SIDE else PATCH_COLOR
        pen = QPen(color)
        pen.setWidthF(_DETAIL_PEN_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        if side == _EAR_ACCENT_SIDE:
            inner_x, outer_x = center.x() + side * 17, center.x() + side * 30
        else:
            inner_x, outer_x = center.x() + side * 9, center.x() + side * 24
        wy = center.y() + _WHISKER_Y_OFFSET
        for row in _WHISKER_ROWS:
            painter.drawLine(QPointF(inner_x, wy + row), QPointF(outer_x, wy + row * 1.6))
    painter.restore()


# -- eyes + mouth -------------------------------------------------------------
# The confirmed default: simple filled-circle dot eyes (no crescents) and a
# small simple mouth. Closed/squinted states use a thin single stroked
# curve instead of a dot -- still simple, never a filled crescent shape.

_EYE_DX = 12.0
_EYE_Y_OFFSET = -4.0
_EYE_RADIUS = 4.4
_MOUTH_Y_OFFSET = 12.0


def _draw_eye_dot(painter: QPainter, ex: float, ey: float, radius: float = _EYE_RADIUS) -> None:
    painter.setPen(Qt.NoPen)
    painter.setBrush(OUTLINE_COLOR)
    painter.drawEllipse(QPointF(ex, ey), radius, radius)


def _draw_eye_curve(
    painter: QPainter, ex: float, ey: float, half_width: float = 5.5, bulge: float = 3.0
) -> None:
    pen = QPen(OUTLINE_COLOR)
    pen.setWidthF(_DETAIL_PEN_WIDTH)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(ex - half_width, ey))
    path.quadTo(QPointF(ex, ey + bulge), QPointF(ex + half_width, ey))
    painter.drawPath(path)


def _mouth_pen() -> QPen:
    pen = QPen(OUTLINE_COLOR)
    pen.setWidthF(_DETAIL_PEN_WIDTH)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _draw_face(painter: QPainter, center: QPointF, mood: Mood, t: float) -> None:
    if mood == Mood.IDLE:
        _draw_idle_face(painter, center, t)
    elif mood == Mood.HAPPY:
        _draw_happy_face(painter, center)
    else:
        _draw_waiting_face(painter, center, t)


# A brief periodic blink -- eyes swap from open dots to a closed curve for a
# short window every cycle -- the one piece of "discrete" timing kept in an
# otherwise continuous style, since real blinking reads as a snap, not a
# smooth morph; every other animation here is a plain continuous sine.
_BLINK_CYCLE_SECONDS = 4.0
_BLINK_DURATION_SECONDS = 0.16


def _is_blinking(t: float) -> bool:
    return (t % _BLINK_CYCLE_SECONDS) < _BLINK_DURATION_SECONDS


def _draw_idle_face(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    eye_y = center.y() + _EYE_Y_OFFSET
    blinking = _is_blinking(t)
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX
        if blinking:
            _draw_eye_curve(painter, ex, eye_y, half_width=5.0, bulge=2.0)
        else:
            _draw_eye_dot(painter, ex, eye_y)

    mouth_y = center.y() + _MOUTH_Y_OFFSET
    painter.setPen(_mouth_pen())
    path = QPainterPath(QPointF(center.x() - 4, mouth_y))
    path.quadTo(QPointF(center.x(), mouth_y + 3), QPointF(center.x() + 4, mouth_y))
    painter.drawPath(path)
    painter.restore()


def _draw_happy_face(painter: QPainter, center: QPointF) -> None:
    painter.save()
    eye_y = center.y() + _EYE_Y_OFFSET + 2
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX
        _draw_eye_curve(painter, ex, eye_y, half_width=5.5, bulge=-4.5)

    mouth_y = center.y() + _MOUTH_Y_OFFSET - 1
    painter.setPen(_mouth_pen())
    path = QPainterPath(QPointF(center.x() - 8, mouth_y - 2))
    path.quadTo(QPointF(center.x(), mouth_y + 7), QPointF(center.x() + 8, mouth_y - 2))
    painter.drawPath(path)
    painter.restore()


def _draw_waiting_face(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    glance = 1.6 * math.sin(t * 1.3)
    eye_y = center.y() + _EYE_Y_OFFSET
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX + glance
        _draw_eye_dot(painter, ex, eye_y, radius=4.0)

    mouth_y = center.y() + _MOUTH_Y_OFFSET
    painter.setPen(_mouth_pen())
    path = QPainterPath(QPointF(center.x() - 5, mouth_y))
    path.quadTo(QPointF(center.x(), mouth_y - 3), QPointF(center.x() + 5, mouth_y))
    painter.drawPath(path)
    painter.restore()


def _draw_purr_face(painter: QPainter, center: QPointF, t: float) -> None:
    """A content, slightly-squinted look while the mouse hovers over the
    cat -- distinct from IDLE's periodic blink and HAPPY's wide smile."""
    painter.save()
    eye_y = center.y() + _EYE_Y_OFFSET + 1
    squint = 0.6 + 0.15 * math.sin(t * 2.5)
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX
        _draw_eye_curve(painter, ex, eye_y, half_width=5.0, bulge=3.0 * squint)

    mouth_y = center.y() + _MOUTH_Y_OFFSET - 2
    painter.setPen(_mouth_pen())
    path = QPainterPath(QPointF(center.x() - 5, mouth_y - 1))
    path.quadTo(QPointF(center.x(), mouth_y + 4), QPointF(center.x() + 5, mouth_y - 1))
    painter.drawPath(path)
    painter.restore()


def _draw_focused_face(painter: QPainter, center: QPointF, t: float) -> None:
    """An intent, unblinking stare while a matching test/build process runs
    -- fixed dead-ahead dot eyes (a slow size pulse standing in for
    "concentrating") and a flat, neutral mouth, no eyebrows/worry lines."""
    painter.save()
    eye_y = center.y() + _EYE_Y_OFFSET - 1
    pulse = _EYE_RADIUS + 0.5 * math.sin(t * 2.2)
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX
        _draw_eye_dot(painter, ex, eye_y, radius=pulse)

    mouth_y = center.y() + _MOUTH_Y_OFFSET
    painter.setPen(_mouth_pen())
    painter.drawLine(QPointF(center.x() - 4, mouth_y), QPointF(center.x() + 4, mouth_y))
    painter.restore()


def _draw_sleep_face(painter: QPainter, center: QPointF, t: float) -> None:
    """The AWAY deep-sleep face: fully flat closed-eye lines -- distinct
    from IDLE's occasional curved blink -- and a tiny closed mouth."""
    painter.save()
    eye_y = center.y() + _EYE_Y_OFFSET + 3
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX
        _draw_eye_curve(painter, ex, eye_y, half_width=4.6, bulge=0.8)

    mouth_y = center.y() + _MOUTH_Y_OFFSET - 4
    painter.setPen(_mouth_pen())
    painter.drawLine(QPointF(center.x() - 2, mouth_y), QPointF(center.x() + 2, mouth_y))
    painter.restore()


# "Curious" (v1.6): a new program was just detected launching. Perked ears
# like "focused", but rotated together with the head around its own center
# -- a head-tilt -- which is what keeps this from reading as a near-
# duplicate of the focused stare.
_CURIOSITY_TILT_DEGREES = 14.0


def _draw_curious_face(painter: QPainter, center: QPointF, t: float) -> None:
    """Wide dot eyes held steadily off to one side (looking at whatever
    just appeared) and a small round open "o" mouth -- distinct from
    FOCUSED's fixed pupils/flat mouth and WAITING's side-to-side glancing/
    worried mouth."""
    painter.save()
    eye_y = center.y() + _EYE_Y_OFFSET - 1
    shift = 2.6
    for side in (-1, 1):
        ex = center.x() + side * _EYE_DX + shift
        _draw_eye_dot(painter, ex, eye_y, radius=4.6)

    mouth_y = center.y() + _MOUTH_Y_OFFSET
    painter.setPen(_mouth_pen())
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(center.x(), mouth_y), 2.6, 2.6)
    painter.restore()


def _draw_face_turned(painter: QPainter, center: QPointF, stage: int, t: float) -> None:
    """Sulking back-view poses, stages 0-3 ("fully reconciled" -- stage 4 --
    is just the normal front view, handled by the caller falling through to
    `_draw_face` once `turn_stage` goes back to `None`). The head/ears/
    patch are already drawn normally by the caller; only the face itself
    (and the blush/whisker detail, deliberately skipped here -- see
    `_draw_face_details`'s own docstring) differs. Each stage reveals a bit
    more face, as if glancing back over a shoulder."""
    painter.save()

    seam_pen = _outline_pen(_DETAIL_PEN_WIDTH)
    seam_color = QColor(OUTLINE_COLOR)
    seam_color.setAlpha(int(150 * (1.0 - stage / 3.0)))
    seam_pen.setColor(seam_color)
    painter.setPen(seam_pen)
    painter.drawLine(QPointF(center.x(), center.y() - 16), QPointF(center.x(), center.y() + 10))

    if stage <= 0:
        painter.restore()
        return

    reveal = stage / 3.0
    visible_sides = (1,) if stage == 1 else (-1, 1)
    eye_y = center.y() + _EYE_Y_OFFSET
    for side in visible_sides:
        ex = center.x() + side * (5 + 6 * reveal)
        _draw_eye_dot(painter, ex, eye_y, radius=2.0 + 2.5 * reveal)

    if stage >= 3:
        mouth_y = center.y() + _MOUTH_Y_OFFSET
        painter.setPen(_mouth_pen())
        path = QPainterPath(QPointF(center.x() - 3, mouth_y))
        path.quadTo(QPointF(center.x(), mouth_y + 2), QPointF(center.x() + 3, mouth_y))
        painter.drawPath(path)

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
    painter.save()
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


def _draw_heart(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    pulse = 1.0 + 0.12 * math.sin(t * 5.0)
    hx = center.x()
    hy = center.y() - BODY_RY * 1.55
    size = 8.0 * pulse

    path = QPainterPath()
    path.moveTo(hx, hy + size * 0.6)
    path.cubicTo(
        QPointF(hx - size * 1.3, hy - size * 0.5),
        QPointF(hx - size * 0.4, hy - size * 1.5),
        QPointF(hx, hy - size * 0.4),
    )
    path.cubicTo(
        QPointF(hx + size * 0.4, hy - size * 1.5),
        QPointF(hx + size * 1.3, hy - size * 0.5),
        QPointF(hx, hy + size * 0.6),
    )
    painter.setPen(Qt.NoPen)
    painter.setBrush(BLUSH_COLOR)
    painter.drawPath(path)

    for i in range(3):
        sparkle_phase = (t * 0.8 + i * 0.33) % 1.0
        sx = hx + (i - 1) * 16
        sy = hy - 14 - sparkle_phase * 14
        alpha = int(255 * (1.0 - sparkle_phase))
        color = QColor("#FFD54F")
        color.setAlpha(max(0, alpha))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(sx, sy), 2.2, 2.2)
    painter.restore()


def _draw_exclaim_bubble(painter: QPainter, center: QPointF, t: float, urgent: bool = False) -> None:
    painter.save()
    bounce = 2.0 * abs(math.sin(t * 3.0))
    bx = center.x() + BODY_RX * 0.55
    by = center.y() - BODY_RY * 1.45 - bounce

    radius = 11.0
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(bx, by), radius, radius)

    font = QFont("Segoe UI", 12, QFont.Bold)
    painter.setFont(font)
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    metrics = QFontMetricsF(font)
    text = "‼" if urgent else "!"
    tw = metrics.horizontalAdvance(text)
    th = metrics.ascent()
    painter.drawText(QPointF(bx - tw / 2, by + th / 2 - 1), text)
    painter.restore()


# -- status badges ------------------------------------------------------
# A separate overlay layer from mood, at most one small icon near the
# top-left of the head. v1.17: still its own smaller-than-the-character
# outline width (this round's small chrome gets restyled to match the new
# bolder body outline too, per the spec's Part 4, but literally reusing
# `_OUTLINE_PEN_WIDTH` at this ~6-12-unit icon scale would swallow the
# shapes into blobs, the same lesson v1.15 already recorded).
_SMALL_ICON_OUTLINE_WIDTH = 2.2

_BADGE_POS_OFFSET = QPointF(-BODY_RX * 0.85, -BODY_RY * 1.15)


def _draw_status_badge(painter: QPainter, center: QPointF, badge: Badge, t: float) -> None:
    pos = QPointF(center.x() + _BADGE_POS_OFFSET.x(), center.y() + _BADGE_POS_OFFSET.y())

    if badge == Badge.CRITICAL_BATTERY:
        _draw_battery_icon(painter, pos, QColor("#E53935"), pulse_speed=6.0, t=t)
    elif badge == Badge.LOW_BATTERY:
        _draw_battery_icon(painter, pos, QColor("#FB8C00"), pulse_speed=1.6, t=t)
    elif badge == Badge.CHARGING:
        _draw_lightning_icon(painter, pos)
    elif badge == Badge.HIGH_RESOURCE:
        _draw_sweat_drop_icon(painter, pos, t)
    elif badge == Badge.LOW_DISK:
        _draw_disk_warning_icon(painter, pos)


def _draw_battery_icon(
    painter: QPainter, pos: QPointF, color: QColor, pulse_speed: float, t: float
) -> None:
    painter.save()
    alpha = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * pulse_speed))
    fill = QColor(color)
    fill.setAlphaF(alpha)

    body = QRectF(0, 0, 13.0, 8.0)
    body.moveCenter(pos)
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(fill)
    painter.drawRoundedRect(body, 1.5, 1.5)

    nub = QRectF(0, 0, 1.6, 3.6)
    nub.moveCenter(QPointF(body.right() + 1.0, pos.y()))
    painter.setPen(Qt.NoPen)
    painter.setBrush(fill)
    painter.drawRect(nub)

    inner = body.adjusted(2.0, 2.0, -6.0, -2.0)
    painter.setBrush(color)
    painter.drawRect(inner)
    painter.restore()


def _draw_lightning_icon(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(QColor("#FDD835"))
    path = QPainterPath(QPointF(pos.x() - 1.5, pos.y() - 7.0))
    path.lineTo(QPointF(pos.x() + 3.0, pos.y() - 7.0))
    path.lineTo(QPointF(pos.x() - 1.0, pos.y() + 0.5))
    path.lineTo(QPointF(pos.x() + 2.5, pos.y() + 0.5))
    path.lineTo(QPointF(pos.x() - 3.0, pos.y() + 7.0))
    path.lineTo(QPointF(pos.x() + 0.5, pos.y() - 0.5))
    path.lineTo(QPointF(pos.x() - 2.5, pos.y() - 0.5))
    path.closeSubpath()
    painter.drawPath(path)
    painter.restore()


def _draw_sweat_drop_icon(painter: QPainter, pos: QPointF, t: float) -> None:
    painter.save()
    bob = 1.2 * math.sin(t * 3.0)
    dx, dy = pos.x(), pos.y() + bob
    size = 6.0

    path = QPainterPath()
    path.moveTo(dx, dy - size)
    path.cubicTo(
        QPointF(dx - size * 0.9, dy + size * 0.2),
        QPointF(dx - size * 0.5, dy + size),
        QPointF(dx, dy + size),
    )
    path.cubicTo(
        QPointF(dx + size * 0.5, dy + size),
        QPointF(dx + size * 0.9, dy + size * 0.2),
        QPointF(dx, dy - size),
    )
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(QColor("#4FC3F7"))
    painter.drawPath(path)
    painter.restore()


def _draw_disk_warning_icon(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    disk_rect = QRectF(0, 0, 12.0, 12.0)
    disk_rect.moveCenter(QPointF(pos.x() - 2.0, pos.y()))
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(QColor("#B0BEC5"))
    painter.drawEllipse(disk_rect)
    hole_rect = QRectF(0, 0, 4.0, 4.0)
    hole_rect.moveCenter(disk_rect.center())
    painter.setBrush(WHITE)
    painter.drawEllipse(hole_rect)

    warn_center = QPointF(pos.x() + 6.0, pos.y() + 4.0)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FFB300"))
    tri = [
        QPointF(warn_center.x(), warn_center.y() - 6.0),
        QPointF(warn_center.x() - 5.2, warn_center.y() + 4.0),
        QPointF(warn_center.x() + 5.2, warn_center.y() + 4.0),
    ]
    _draw_polygon(painter, tri)

    font = QFont("Segoe UI", 6, QFont.Bold)
    painter.setFont(font)
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.drawText(QPointF(warn_center.x() - 1.2, warn_center.y() + 2.2), "!")
    painter.restore()


def _draw_polygon(painter: QPainter, pts) -> None:
    path = QPainterPath()
    path.moveTo(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    path.closeSubpath()
    painter.drawPath(path)


# -- commit streak ---------------------------------------------------------

_STREAK_POS_OFFSET = QPointF(BODY_RX * 0.85, -BODY_RY * 1.15)


def _draw_streak_icon(painter: QPainter, center: QPointF, streak: int, t: float) -> None:
    pos = QPointF(center.x() + _STREAK_POS_OFFSET.x(), center.y() + _STREAK_POS_OFFSET.y())
    if streak >= 30:
        _draw_crown_icon(painter, pos)
    elif streak >= 7:
        _draw_star_icon(painter, pos, radius=7.5, color=QColor("#FFD700"), t=t)
    else:
        _draw_star_icon(painter, pos, radius=5.0, color=QColor("#B0BEC5"), t=t)


def _star_points(center: QPointF, outer_r: float, inner_r: float) -> list[QPointF]:
    points = []
    for i in range(10):
        r = outer_r if i % 2 == 0 else inner_r
        angle = math.pi / 2 + i * math.pi / 5
        points.append(QPointF(center.x() + r * math.cos(angle), center.y() - r * math.sin(angle)))
    return points


def _draw_star_icon(painter: QPainter, pos: QPointF, radius: float, color: QColor, t: float) -> None:
    painter.save()
    twinkle = 0.85 + 0.15 * math.sin(t * 3.0)
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(color)
    _draw_polygon(painter, _star_points(pos, radius * twinkle, radius * 0.42))
    painter.restore()


def _draw_crown_icon(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    w, h = 15.0, 9.0
    base_y = pos.y() + h * 0.5
    left_x = pos.x() - w / 2
    points = [
        QPointF(left_x, base_y),
        QPointF(left_x, base_y - h),
        QPointF(left_x + w * 0.25, base_y - h * 0.4),
        QPointF(left_x + w * 0.5, base_y - h * 1.15),
        QPointF(left_x + w * 0.75, base_y - h * 0.4),
        QPointF(left_x + w, base_y - h),
        QPointF(left_x + w, base_y),
    ]
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(QColor("#FFD700"))
    _draw_polygon(painter, points)
    painter.restore()


# -- particles --------------------------------------------------------------

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


# -- distraction nudge / high five paws --------------------------------------


def _draw_nudge_wave(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    swing = math.sin(t * 8.0)
    paw_x = center.x() + BODY_RX * 0.95
    paw_y = center.y() + BODY_RY * 0.1 - 8.0 * max(0.0, swing)

    painter.setPen(_outline_pen())
    painter.setBrush(SECONDARY_FILL_COLOR)
    painter.drawEllipse(QPointF(paw_x, paw_y), 6.5, 6.5)
    painter.restore()


def _draw_high_five_paw(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    wobble = 1.5 * math.sin(t * 10.0)
    paw_x = center.x() + BODY_RX * 0.85 + wobble
    paw_y = center.y() - BODY_RY * 0.75

    painter.setPen(_outline_pen())
    painter.setBrush(SECONDARY_FILL_COLOR)
    pad_radius = 7.5
    painter.drawEllipse(QPointF(paw_x, paw_y), pad_radius, pad_radius)
    for dx in (-4.0, 0.0, 4.0):
        toe = QPointF(paw_x + dx, paw_y - pad_radius + 1.5)
        painter.drawEllipse(toe, 2.2, 2.2)
    painter.restore()


# -- distraction/reminder speech bubble --------------------------------------
# Unchanged from v1.14/v1.15/v1.16 -- the bubble card itself is theme.py-era
# UI chrome, not "the cat/mouse sprite art" this round's spec scopes itself
# to.

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
    """The natural (unclamped) single-line bubble size, in canvas units --
    the single source of truth shared between `_draw_speech_bubble`'s
    actual drawing and `KittenWindow._grow_for_nudge` (window.py)."""
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


# -- seasonal accessories -----------------------------------------------------

_ACCESSORY_POS = QPointF(0.0, -BODY_RY * 1.55)


def _draw_accessory(painter: QPainter, center: QPointF, accessory: str, t: float) -> None:
    pos = QPointF(center.x() + _ACCESSORY_POS.x(), center.y() + _ACCESSORY_POS.y())
    if accessory == "halloween":
        _draw_witch_hat(painter, pos)
    elif accessory == "yalda":
        _draw_pomegranate_hat(painter, pos)
    elif accessory == "birthday":
        _draw_party_hat(painter, pos)


def _draw_witch_hat(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(QColor("#2B2B33"))

    brim = QRectF(0, 0, 28.0, 6.0)
    brim.moveCenter(QPointF(pos.x(), pos.y() + 6.0))
    painter.drawEllipse(brim)

    cone = QPainterPath(QPointF(pos.x() - 9.0, pos.y() + 4.0))
    cone.lineTo(QPointF(pos.x() + 2.0, pos.y() - 20.0))
    cone.lineTo(QPointF(pos.x() + 9.0, pos.y() + 4.0))
    cone.closeSubpath()
    painter.drawPath(cone)

    band = QRectF(0, 0, 20.0, 4.0)
    band.moveCenter(QPointF(pos.x() - 0.5, pos.y() + 0.5))
    painter.setBrush(QColor("#7B4FA0"))
    painter.setPen(Qt.NoPen)
    painter.drawRect(band)
    painter.restore()


def _draw_pomegranate_hat(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    painter.setBrush(QColor("#B32B3A"))
    body = QRectF(0, 0, 16.0, 15.0)
    body.moveCenter(QPointF(pos.x(), pos.y() + 3.0))
    painter.drawEllipse(body)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#5C8A4A"))
    crown = [
        QPointF(pos.x() - 4.0, pos.y() - 3.5),
        QPointF(pos.x(), pos.y() - 10.0),
        QPointF(pos.x() + 4.0, pos.y() - 3.5),
    ]
    _draw_polygon(painter, crown)
    painter.restore()


_PARTY_HAT_COLOR = QColor("#42A5F5")


def _draw_party_hat(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    painter.setPen(_outline_pen(_SMALL_ICON_OUTLINE_WIDTH))
    cone = QPainterPath(QPointF(pos.x() - 9.0, pos.y() + 5.0))
    cone.lineTo(QPointF(pos.x(), pos.y() - 18.0))
    cone.lineTo(QPointF(pos.x() + 9.0, pos.y() + 5.0))
    cone.closeSubpath()

    painter.setBrush(_PARTY_HAT_COLOR)
    painter.drawPath(cone)

    painter.setPen(Qt.NoPen)
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(pos.x(), pos.y() - 18.0), 2.5, 2.5)
    painter.restore()


# -- mouse (v1.7 chase minigame) --------------------------------------------
# Its own small logical canvas, same style family as the restyled cat (bold
# outline, flat fill) but its own simple palette -- "its own small palette
# choice is your call" per the spec, kept a plain cool slate gray as before
# so it still reads as clearly "not the cat" at a glance.

MOUSE_CANVAS = 64.0
_MOUSE_CENTER = QPointF(MOUSE_CANVAS / 2, MOUSE_CANVAS / 2 + 4)
_MOUSE_BODY_COLOR = QColor("#AEB4BD")
_MOUSE_BODY_RX, _MOUSE_BODY_RY = 15.0, 11.0
_MOUSE_TAIL_WIDTH = 3.0
_MOUSE_OUTLINE_WIDTH = _OUTLINE_PEN_WIDTH * (MOUSE_CANVAS / CANVAS)


def _mouse_outline_pen(width: float = _MOUSE_OUTLINE_WIDTH) -> QPen:
    pen = QPen(OUTLINE_COLOR)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def paint_mouse(painter: QPainter, rect: QRectF, t: float) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    scale = min(rect.width(), rect.height()) / MOUSE_CANVAS
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.translate(-MOUSE_CANVAS / 2, -MOUSE_CANVAS / 2)

    breathe = 1.0 + 0.02 * math.sin(t * 2.4)
    center = _MOUSE_CENTER

    _draw_mouse_tail(painter, center)
    _draw_mouse_ears(painter, center)
    _draw_mouse_body(painter, center, breathe)
    _draw_mouse_face(painter, center)

    painter.restore()


def _draw_mouse_body(painter: QPainter, center: QPointF, breathe: float) -> None:
    painter.save()
    rect = QRectF(0, 0, _MOUSE_BODY_RX * 2, _MOUSE_BODY_RY * 2 * breathe)
    rect.moveCenter(center)
    painter.setPen(_mouse_outline_pen())
    painter.setBrush(_MOUSE_BODY_COLOR)
    painter.drawEllipse(rect)
    painter.restore()


def _draw_mouse_ears(painter: QPainter, center: QPointF) -> None:
    painter.save()
    painter.setPen(_mouse_outline_pen())
    painter.setBrush(SECONDARY_FILL_COLOR)
    ear_y = center.y() - _MOUSE_BODY_RY * 0.95
    for side in (-1, 1):
        ex = center.x() + side * _MOUSE_BODY_RX * 0.55
        painter.drawEllipse(QPointF(ex, ear_y), 6.5, 6.5)
    painter.restore()


def _draw_mouse_tail(painter: QPainter, center: QPointF) -> None:
    painter.save()
    base = QPointF(center.x() + _MOUSE_BODY_RX * 0.8, center.y() + _MOUSE_BODY_RY * 0.3)
    c1 = QPointF(base.x() + 14, base.y() + 8)
    c2 = QPointF(base.x() + 4, base.y() + 20)
    end = QPointF(base.x() + 16, base.y() + 22)

    path = QPainterPath(base)
    path.cubicTo(c1, c2, end)

    outline = _mouse_outline_pen(_MOUSE_TAIL_WIDTH + _MOUSE_OUTLINE_WIDTH * 1.2)
    painter.setPen(outline)
    painter.drawPath(path)

    fill = QPen(_MOUSE_BODY_COLOR, _MOUSE_TAIL_WIDTH, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(fill)
    painter.drawPath(path)
    painter.restore()


def _draw_mouse_face(painter: QPainter, center: QPointF) -> None:
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(OUTLINE_COLOR)
    eye_y = center.y() - _MOUSE_BODY_RY * 0.2
    for side in (-1, 1):
        ex = center.x() + side * _MOUSE_BODY_RX * 0.4
        painter.drawEllipse(QPointF(ex, eye_y), 2.2, 2.2)
    painter.restore()
