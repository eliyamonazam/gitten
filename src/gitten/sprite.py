"""QPainter drawing code for the kitten.

Everything is drawn with primitive shapes (ellipses, triangles, painter
paths) in a fixed 128x128 logical coordinate space -- no external art
assets. `paint_kitten` is pure with respect to Qt widget state: give it a
painter, a target rect, a mood, and a monotonically increasing time in
seconds, and it draws one animated frame.
"""

from __future__ import annotations

import math
from contextlib import contextmanager

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from gitten.mood import Mood
from gitten.status_badge import Badge

BODY_COLOR = QColor("#E8935F")
BODY_HIGHLIGHT = QColor("#F7B98F")
INNER_EAR_COLOR = QColor("#F5B98A")
OUTLINE_COLOR = QColor("#2C2C2A")
WHITE = QColor("#FFFFFF")
SHADOW_COLOR = QColor(0, 0, 0, 60)
ZZZ_COLOR = QColor(120, 120, 128, 220)

CANVAS = 128.0
CENTER = QPointF(CANVAS / 2, 70.0)
BODY_RX, BODY_RY = 34.0, 30.0

_OUTLINE_PEN_WIDTH = 2.6


def _outline_pen(width: float = _OUTLINE_PEN_WIDTH) -> QPen:
    pen = QPen(OUTLINE_COLOR)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


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

    breathe = 1.0 + 0.018 * math.sin(t * 2.0)
    # v1.8: the AWAY "deep sleep" pose breathes noticeably slower and deeper
    # than the regular idle breathing above -- the spec's explicit ask for
    # something "visibly different from regular idle side by side, the same
    # bar already applied to distinguishing focused from curious."
    away_breathe = 1.0 + 0.05 * math.sin(t * 0.7)
    bob = 1.5 * math.sin(t * 2.0) if not dragging else 0.0
    tail_phase = math.sin(t * 1.6) * 0.5 + math.sin(t * 0.7) * 0.2
    # The WAITING mood's nervous shiver is itself a mood reaction, so it
    # must not leak through while AWAY -- the whole point of the override
    # below is that the pose becomes mood-independent. Caught concretely by
    # this feature's own pixel-diff verification (see DEVELOPMENT_NOTES.md):
    # an early version diffed non-zero between an away-IDLE and away-WAITING
    # render because this line ignored `away`.
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
    # override rather than another layer -- decided (not just reasoned
    # about) because the whole point of this state is "nobody is here to
    # see any of this": a sulking cat has no one to perform sulking at, a
    # hover/curious/focused reaction has no one to perform for, and none of
    # those poses are even reachable in practice while genuinely away (they
    # all require live mouse/keyboard input or an active process check that
    # v1.8's own suppression already gates out). So while away, the cat
    # always lies down and sleeps regardless of mood/sulk/reaction state,
    # exactly like v1.6's curious-vs-focused decision was verified with a
    # concrete pixel-diff rather than left as reasoning alone -- see
    # DEVELOPMENT_NOTES.md for that diff.
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
    # The curled AWAY tail is drawn after the (wider, flattened) lying body
    # rather than before it, unlike the regular swaying tail -- otherwise
    # the lying body's wider footprint completely covers it, since it's
    # tucked in close. Caught by looking at an actual rendered image (not
    # just the pixel-diff counts, which only check for *some* difference,
    # not that the difference looks right) -- see DEVELOPMENT_NOTES.md.
    if not show_away:
        _draw_tail(painter, center, tail_phase)
    if show_away:
        # Ears relax and splay outward/down instead of the default upright
        # posture -- paired with the lying-down body below, this is the
        # other half of "visibly different from regular idle."
        _draw_ears(painter, center, breathe, drooping=True, t=t)
    elif show_curious:
        # A brief head-tilt (ears + face rotated together around the head's
        # own center, body/tail left alone) is what makes "curious" read as
        # "noticing something new" rather than a near-duplicate of
        # "focused"'s straight-ahead perked-ears stare.
        with _head_tilt(painter, center, _CURIOSITY_TILT_DEGREES):
            _draw_ears(painter, center, breathe, perked=True, wiggle=False, t=t)
    else:
        _draw_ears(painter, center, breathe, perked=show_focused, wiggle=show_purr, t=t)
    _draw_body(
        painter, center, away_breathe if show_away else breathe, night=night, lying=show_away
    )
    if show_away:
        _draw_tail(painter, center, tail_phase, curled=True)
        _draw_sleep_face(painter, center, t)
    elif turn_stage is not None:
        _draw_face_turned(painter, center, turn_stage, t)
    elif show_purr:
        _draw_purr_face(painter, center, t)
    elif show_curious:
        with _head_tilt(painter, center, _CURIOSITY_TILT_DEGREES):
            _draw_curious_face(painter, center, t)
    elif show_focused:
        _draw_focused_face(painter, center, t)
    else:
        _draw_face(painter, center, mood, t)
        urgent = badge in (Badge.LOW_BATTERY, Badge.CRITICAL_BATTERY)
        _draw_mood_overlay(painter, center, mood, t, urgent=urgent)

    if show_away:
        # A bigger, slower-drifting "zzz" than the regular IDLE mood
        # overlay -- reused (not reinvented) via the `deep` flag, played
        # unconditionally regardless of the git-driven mood underneath,
        # per the override decision above.
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


def _draw_tail(painter: QPainter, center: QPointF, phase: float, curled: bool = False) -> None:
    painter.save()
    pen = _outline_pen(9.0)
    pen.setColor(BODY_COLOR)
    painter.setPen(pen)

    if curled:
        # Tucked in close to the body in a small curled loop instead of
        # swaying -- reads as "settled down to sleep" rather than
        # alert/active (v1.8 AWAY pose). Anchored a bit closer to center
        # than the regular base since the lying-down body is flatter/wider.
        base = QPointF(center.x() + BODY_RX * 0.55, center.y() + BODY_RY * 0.25)
        c1 = QPointF(base.x() + 12, base.y() + 2)
        c2 = QPointF(base.x() + 8, base.y() - 12)
        end = QPointF(base.x() - 4, base.y() - 8)
    else:
        base = QPointF(center.x() + BODY_RX * 0.75, center.y() + BODY_RY * 0.55)
        sway = 14.0 * phase
        c1 = QPointF(base.x() + 22, base.y() + 6 + sway * 0.4)
        c2 = QPointF(base.x() + 26, base.y() - 20 + sway)
        end = QPointF(base.x() + 14, base.y() - 34 + sway * 1.3)

    path = QPainterPath(base)
    path.cubicTo(c1, c2, end)
    painter.drawPath(path)

    # thin dark outline stroke on top for definition
    outline = _outline_pen(1.4)
    painter.setPen(outline)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    painter.restore()


def _draw_ears(
    painter: QPainter,
    center: QPointF,
    breathe: float,
    perked: bool = False,
    wiggle: bool = False,
    t: float = 0.0,
    drooping: bool = False,
) -> None:
    painter.save()
    painter.setPen(_outline_pen())
    # "Perked" (focus reaction): ears stand taller and lean in toward the
    # center, an alert/attentive posture, instead of the normal relaxed angle.
    # "Drooping" (v1.8 AWAY pose): the opposite extreme -- flattened and
    # splayed further outward, a relaxed/asleep posture, distinct from both
    # the perked and the default resting angle.
    height_scale = 1.3 if perked else (0.4 if drooping else 1.0)
    lean = 0.5 if perked else (1.6 if drooping else 1.0)
    # "Wiggle" (purr reaction): a slow, gentle side-to-side sway on the ear
    # tips -- the same sine-wave idiom already used for breathing/tail sway,
    # applied here instead of a static lean.
    sway = 2.5 * math.sin(t * 3.0) if wiggle else 0.0
    for side in (-1, 1):
        ex = center.x() + side * BODY_RX * 0.62
        ey = center.y() - BODY_RY * 0.82
        outer = [
            QPointF(ex - 13 * side, ey + 6),
            QPointF(ex + 4 * side * lean + sway, ey - 24 * breathe * height_scale),
            QPointF(ex + 15 * side, ey + 10),
        ]
        painter.setBrush(BODY_COLOR)
        _draw_polygon(painter, outer)

        inner = [
            QPointF(ex - 6 * side, ey + 3),
            QPointF(ex + 3 * side * lean + sway, ey - 12 * breathe * height_scale),
            QPointF(ex + 9 * side, ey + 5),
        ]
        painter.setPen(Qt.NoPen)
        painter.setBrush(INNER_EAR_COLOR)
        _draw_polygon(painter, inner)
        painter.setPen(_outline_pen())
    painter.restore()


def _draw_polygon(painter: QPainter, pts) -> None:
    path = QPainterPath()
    path.moveTo(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    path.closeSubpath()
    painter.drawPath(path)


_MOONLIT_BASE = QColor("#3B4A6B")
_MOONLIT_HIGHLIGHT = QColor("#5C6F99")
_NIGHT_BLEND_FACTOR = 0.45


def _blend_color(a: QColor, b: QColor, factor: float) -> QColor:
    """Linear-interpolate two colors; factor 0.0 = a, 1.0 = b."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * factor),
        round(a.green() + (b.green() - a.green()) * factor),
        round(a.blue() + (b.blue() - a.blue()) * factor),
    )


def _draw_body(
    painter: QPainter, center: QPointF, breathe: float, night: bool = False, lying: bool = False
) -> None:
    painter.save()
    # v1.8 AWAY pose: "the cat lies down rather than sits" -- a noticeably
    # wider, flatter ellipse instead of the regular upright oval, the main
    # thing that makes this pose read as visibly different from IDLE at a
    # glance rather than a near-duplicate with a different face.
    rx = BODY_RX * 1.4 if lying else BODY_RX
    ry = BODY_RY * 0.55 if lying else BODY_RY
    rect = QRectF(0, 0, rx * 2, ry * 2 * breathe)
    rect.moveCenter(center)

    if night:
        base_color = _blend_color(BODY_COLOR, _MOONLIT_BASE, _NIGHT_BLEND_FACTOR)
        highlight_color = _blend_color(BODY_HIGHLIGHT, _MOONLIT_HIGHLIGHT, _NIGHT_BLEND_FACTOR)
    else:
        base_color = BODY_COLOR
        highlight_color = BODY_HIGHLIGHT

    gradient = QRadialGradient(
        QPointF(center.x() - BODY_RX * 0.35, center.y() - BODY_RY * 0.5),
        BODY_RX * 1.6,
    )
    gradient.setColorAt(0.0, highlight_color)
    gradient.setColorAt(1.0, base_color)

    painter.setPen(_outline_pen())
    painter.setBrush(gradient)
    painter.drawEllipse(rect)
    painter.restore()


def _draw_face(painter: QPainter, center: QPointF, mood: Mood, t: float) -> None:
    if mood == Mood.IDLE:
        _draw_idle_face(painter, center)
    elif mood == Mood.HAPPY:
        _draw_happy_face(painter, center)
    else:
        _draw_waiting_face(painter, center, t)


def _draw_idle_face(painter: QPainter, center: QPointF) -> None:
    painter.save()
    pen = _outline_pen(2.2)
    painter.setPen(pen)
    eye_y = center.y() - 2
    for side in (-1, 1):
        ex = center.x() + side * 11
        path = QPainterPath(QPointF(ex - 5, eye_y))
        path.quadTo(QPointF(ex, eye_y + 3), QPointF(ex + 5, eye_y))
        painter.drawPath(path)

    mouth_y = center.y() + 10
    path = QPainterPath(QPointF(center.x() - 4, mouth_y))
    path.quadTo(QPointF(center.x(), mouth_y + 3), QPointF(center.x() + 4, mouth_y))
    painter.drawPath(path)
    painter.restore()


def _draw_happy_face(painter: QPainter, center: QPointF) -> None:
    painter.save()
    pen = _outline_pen(2.4)
    painter.setPen(pen)
    eye_y = center.y() - 3
    for side in (-1, 1):
        ex = center.x() + side * 11
        path = QPainterPath(QPointF(ex - 6, eye_y + 3))
        path.quadTo(QPointF(ex, eye_y - 6), QPointF(ex + 6, eye_y + 3))
        painter.drawPath(path)

    mouth_y = center.y() + 9
    path = QPainterPath(QPointF(center.x() - 8, mouth_y - 2))
    path.quadTo(QPointF(center.x(), mouth_y + 7), QPointF(center.x() + 8, mouth_y - 2))
    painter.drawPath(path)
    painter.restore()


def _draw_waiting_face(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    look = 1.4 * math.sin(t * 1.3)
    eye_y = center.y() - 3

    for side in (-1, 1):
        ex = center.x() + side * 11
        eye_rect = QRectF(0, 0, 11, 11)
        eye_rect.moveCenter(QPointF(ex, eye_y))
        painter.setPen(_outline_pen(1.8))
        painter.setBrush(WHITE)
        painter.drawEllipse(eye_rect)

        pupil_rect = QRectF(0, 0, 4.2, 4.2)
        pupil_rect.moveCenter(QPointF(ex + look, eye_y + 1))
        painter.setPen(Qt.NoPen)
        painter.setBrush(OUTLINE_COLOR)
        painter.drawEllipse(pupil_rect)

        brow_pen = _outline_pen(2.2)
        painter.setPen(brow_pen)
        by = eye_y - 9
        bx0 = QPointF(ex - 6, by + (2 if side < 0 else 0))
        bx1 = QPointF(ex + 6, by + (0 if side < 0 else 2))
        painter.drawLine(bx0, bx1)

    mouth_y = center.y() + 11
    pen = _outline_pen(2.0)
    painter.setPen(pen)
    path = QPainterPath(QPointF(center.x() - 6, mouth_y))
    path.quadTo(QPointF(center.x() - 3, mouth_y + 3), QPointF(center.x(), mouth_y))
    path.quadTo(QPointF(center.x() + 3, mouth_y - 3), QPointF(center.x() + 6, mouth_y))
    painter.drawPath(path)
    painter.restore()


def _draw_purr_face(painter: QPainter, center: QPointF, t: float) -> None:
    """The "purr" reaction: a content, slightly-squinted look while the
    mouse hovers over the cat. Distinct from the IDLE face's fully-closed
    sleepy curves and the HAPPY face's wide upward smile -- squinted but
    still slightly open, with a gentle upward smile and no zzz/heart/bubble
    overlay at all."""
    painter.save()
    pen = _outline_pen(2.2)
    painter.setPen(pen)
    eye_y = center.y() - 2
    squint = 0.6 + 0.1 * math.sin(t * 2.5)
    for side in (-1, 1):
        ex = center.x() + side * 11
        path = QPainterPath(QPointF(ex - 5, eye_y + 1))
        path.quadTo(QPointF(ex, eye_y + 3 * squint), QPointF(ex + 5, eye_y + 1))
        painter.drawPath(path)

    mouth_y = center.y() + 9
    path = QPainterPath(QPointF(center.x() - 5, mouth_y - 1))
    path.quadTo(QPointF(center.x(), mouth_y + 4), QPointF(center.x() + 5, mouth_y - 1))
    painter.drawPath(path)
    painter.restore()


def _draw_focused_face(painter: QPainter, center: QPointF, t: float) -> None:
    """The "focus" reaction: an intent, unblinking stare while a matching
    test/build process is running. Unlike the WAITING face's nervous
    side-to-side glancing, the pupils stay fixed dead ahead -- this is
    watchful, not worried -- with a slow pupil-size pulse standing in for
    "concentrating" and no eyebrows/mouth-worry lines."""
    painter.save()
    eye_y = center.y() - 3
    pupil_pulse = 3.6 + 0.5 * math.sin(t * 2.2)

    for side in (-1, 1):
        ex = center.x() + side * 11
        eye_rect = QRectF(0, 0, 11, 11)
        eye_rect.moveCenter(QPointF(ex, eye_y))
        painter.setPen(_outline_pen(1.8))
        painter.setBrush(WHITE)
        painter.drawEllipse(eye_rect)

        pupil_rect = QRectF(0, 0, pupil_pulse, pupil_pulse)
        pupil_rect.moveCenter(QPointF(ex, eye_y))
        painter.setPen(Qt.NoPen)
        painter.setBrush(OUTLINE_COLOR)
        painter.drawEllipse(pupil_rect)

    mouth_y = center.y() + 10
    painter.setPen(_outline_pen(2.0))
    painter.drawLine(QPointF(center.x() - 4, mouth_y), QPointF(center.x() + 4, mouth_y))
    painter.restore()


def _draw_sleep_face(painter: QPainter, center: QPointF, t: float) -> None:
    """The v1.8 AWAY "deep sleep" face: fully flat, straight closed-eye
    lines -- distinct from IDLE's light-doze downward-curving eyes (a
    curve reads as a relaxed blink; a flat line reads as properly shut) --
    and a tiny closed mouth. Paired with the lying-down body, the drooping
    ears, and the bigger/slower zzz drift, this is meant to be unmistakably
    different from regular IDLE at a glance, not just a relabeled version of
    it."""
    painter.save()
    pen = _outline_pen(2.0)
    painter.setPen(pen)
    eye_y = center.y() - 1
    for side in (-1, 1):
        ex = center.x() + side * 11
        painter.drawLine(QPointF(ex - 5, eye_y), QPointF(ex + 5, eye_y))

    mouth_y = center.y() + 7
    painter.drawLine(QPointF(center.x() - 2, mouth_y), QPointF(center.x() + 2, mouth_y))
    painter.restore()


# "Curious" (v1.6): a new program was just detected launching. Perked ears
# like "focused", but rotated together with the face around the head's own
# center -- a head-tilt -- which is what actually keeps this from reading as
# a near-duplicate of the focused stare.
_CURIOSITY_TILT_DEGREES = 14.0


@contextmanager
def _head_tilt(painter: QPainter, center: QPointF, degrees: float):
    """Rotate everything drawn inside the block by `degrees` around
    `center`, then restore -- used to tilt just the ears+face (not the
    body/tail, which are drawn outside this block) for the curiosity
    reaction."""
    painter.save()
    try:
        painter.translate(center)
        painter.rotate(degrees)
        painter.translate(-center.x(), -center.y())
        yield
    finally:
        painter.restore()


def _draw_curious_face(painter: QPainter, center: QPointF, t: float) -> None:
    """Wide eyes with pupils held steadily off to one side (looking at
    whatever just appeared) and a small round, open "o" mouth -- distinct
    from FOCUSED's fixed-dead-ahead pupils and flat mouth (watching
    intently) and from WAITING's side-to-side glancing and wavy worried
    mouth (anxious). Paired with the caller's head-tilt, this reads as
    "noticing something new" rather than either of those."""
    painter.save()
    eye_y = center.y() - 3
    pupil_shift = 3.0

    for side in (-1, 1):
        ex = center.x() + side * 11
        eye_rect = QRectF(0, 0, 11, 11)
        eye_rect.moveCenter(QPointF(ex, eye_y))
        painter.setPen(_outline_pen(1.8))
        painter.setBrush(WHITE)
        painter.drawEllipse(eye_rect)

        pupil_rect = QRectF(0, 0, 4.6, 4.6)
        pupil_rect.moveCenter(QPointF(ex + pupil_shift, eye_y))
        painter.setPen(Qt.NoPen)
        painter.setBrush(OUTLINE_COLOR)
        painter.drawEllipse(pupil_rect)

    mouth_y = center.y() + 10
    painter.setPen(_outline_pen(1.8))
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(center.x(), mouth_y), 2.6, 2.6)
    painter.restore()


def _draw_face_turned(painter: QPainter, center: QPointF, stage: int, t: float) -> None:
    """Sulking back-view poses, stages 0-3 ("fully reconciled" -- stage 4 --
    is just the normal front view above, handled by the caller). Each stage
    reveals a bit more of the face, as if glancing back over a shoulder,
    without changing body proportions so it still reads as the same cat.
    """
    painter.save()

    # A faint center seam hints at the back of the head; it fades out as the
    # cat turns further toward the viewer.
    seam_pen = _outline_pen(1.6)
    seam_color = QColor(OUTLINE_COLOR)
    seam_color.setAlpha(int(150 * (1.0 - stage / 3.0)))
    seam_pen.setColor(seam_color)
    painter.setPen(seam_pen)
    painter.drawLine(QPointF(center.x(), center.y() - 15), QPointF(center.x(), center.y() + 9))

    if stage <= 0:
        painter.restore()
        return

    # From stage 1, a sliver of face peeks in from one side; by stage 3 both
    # eyes and a small mouth are visible -- close to, but not quite, a full
    # front-facing pose.
    reveal = stage / 3.0
    visible_sides = (1,) if stage == 1 else (-1, 1)
    eye_y = center.y() - 2
    painter.setPen(_outline_pen(2.0))
    for side in visible_sides:
        ex = center.x() + side * (6 + 5 * reveal)
        path = QPainterPath(QPointF(ex - (4 * reveal + 1), eye_y))
        path.quadTo(QPointF(ex, eye_y + 2.5 * reveal), QPointF(ex + 4 * reveal + 1, eye_y))
        painter.drawPath(path)

    if stage >= 3:
        mouth_y = center.y() + 10
        path = QPainterPath(QPointF(center.x() - 3, mouth_y))
        path.quadTo(QPointF(center.x(), mouth_y + 2), QPointF(center.x() + 3, mouth_y))
        painter.drawPath(path)

    painter.restore()


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

    # v1.8 AWAY pose: a noticeably slower drift and bigger letters than the
    # regular IDLE mood's zzz -- "a slower/deeper version of the existing
    # breathing sine-wave" extended to this overlay too, and positioned
    # lower to sit above the flatter lying-down body instead of the taller
    # sitting one.
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
        hx - size * 1.3, hy - size * 0.5,
        hx - size * 0.4, hy - size * 1.5,
        hx, hy - size * 0.4,
    )
    path.cubicTo(
        hx + size * 0.4, hy - size * 1.5,
        hx + size * 1.3, hy - size * 0.5,
        hx, hy + size * 0.6,
    )
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#F06292"))
    painter.drawPath(path)

    for i in range(3):
        sparkle_phase = (t * 0.8 + i * 0.33) % 1.0
        sx = hx + (i - 1) * 16
        sy = hy - 14 - sparkle_phase * 14
        alpha = int(255 * (1.0 - sparkle_phase))
        color = QColor("#FFD54F")
        color.setAlpha(max(0, alpha))
        painter.setBrush(color)
        r = 2.2
        painter.drawEllipse(QPointF(sx, sy), r, r)
    painter.restore()


def _draw_exclaim_bubble(painter: QPainter, center: QPointF, t: float, urgent: bool = False) -> None:
    painter.save()
    bounce = 2.0 * abs(math.sin(t * 3.0))
    bx = center.x() + BODY_RX * 0.55
    by = center.y() - BODY_RY * 1.45 - bounce

    radius = 11.0
    painter.setPen(_outline_pen(2.0))
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(bx, by), radius, radius)

    font = QFont("Segoe UI", 12, QFont.Bold)
    painter.setFont(font)
    painter.setPen(_outline_pen(1.4))
    metrics = QFontMetricsF(font)
    # A low/critical battery badge active at the same moment reads as more
    # urgent than "uncommitted changes" alone -- a pure rendering-time check,
    # no new state machine.
    text = "‼" if urgent else "!"
    tw = metrics.horizontalAdvance(text)
    th = metrics.ascent()
    painter.drawText(QPointF(bx - tw / 2, by + th / 2 - 1), text)
    painter.restore()


# -- status badges ------------------------------------------------------
# A separate overlay layer from mood: at most one small icon shown near the
# top-left of the head, on top of whatever mood is currently displayed.

_BADGE_POS_OFFSET = QPointF(-BODY_RX * 0.85, -BODY_RY * 1.15)


def _draw_status_badge(painter: QPainter, center: QPointF, badge: Badge, t: float) -> None:
    bx = center.x() + _BADGE_POS_OFFSET.x()
    by = center.y() + _BADGE_POS_OFFSET.y()
    pos = QPointF(bx, by)

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
    painter.setPen(_outline_pen(1.2))
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
    painter.setPen(_outline_pen(1.0))
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
    painter.setPen(_outline_pen(1.0))
    painter.setBrush(QColor("#4FC3F7"))
    painter.drawPath(path)
    painter.restore()


def _draw_disk_warning_icon(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    disk_rect = QRectF(0, 0, 12.0, 12.0)
    disk_rect.moveCenter(QPointF(pos.x() - 2.0, pos.y()))
    painter.setPen(_outline_pen(1.1))
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
    painter.setPen(_outline_pen(1.0))
    painter.drawText(QPointF(warn_center.x() - 1.2, warn_center.y() + 2.2), "!")
    painter.restore()


# -- commit streak ---------------------------------------------------------
# A small icon in the top-right corner (mirroring the badge's top-left spot,
# and clear of the mood overlay which lives top-center/right) once the
# streak reaches the spec's 3-day threshold. Nothing below that.

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
    painter.setPen(_outline_pen(1.0))
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
    painter.setPen(_outline_pen(1.0))
    painter.setBrush(QColor("#FFD700"))
    _draw_polygon(painter, points)
    painter.restore()


# -- particles --------------------------------------------------------------
# Generic small fading dots (drag-trail sparkles, the shooting star). Takes
# plain (x, y, opacity) tuples from `particles.ParticleSystem.positions` --
# knows nothing about spawn times or lifespans, purely draws what it's given.

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


# -- distraction nudge ----------------------------------------------------


def _draw_nudge_wave(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    swing = math.sin(t * 8.0)
    paw_x = center.x() + BODY_RX * 0.95
    paw_y = center.y() + BODY_RY * 0.1 - 8.0 * max(0.0, swing)

    pen = _outline_pen(1.6)
    painter.setPen(pen)
    painter.setBrush(BODY_HIGHLIGHT)
    painter.drawEllipse(QPointF(paw_x, paw_y), 6.5, 6.5)
    painter.restore()


# v1.10 bugfix: the bubble's vertical anchor used to be `center.y() -
# BODY_RY * 1.9 - bubble.height() / 2`, which pinned the bubble's *bottom*
# edge at a fixed canvas y of ~13 regardless of its height -- for the
# bubble's actual height (~26 units at this font size), that put its *top*
# edge at roughly y=-13, well above the canvas's own y=0 top edge. Qt clips
# all painting to the widget's own bounds, and this window is only ~130px
# tall with no room above it, so the top half of every nudge bubble ever
# shown -- including the text, vertically centered in that top half -- was
# silently clipped off screen. This was never caught because every prior
# session verified nudges by checking `window._nudge_text` (an internal
# string), never by actually screenshotting a live, positioned window --
# see DEVELOPMENT_NOTES.md's v1.10 bugfix entry for how this was found and
# confirmed with a real QScreen.grabWindow capture. Fixed with a lower,
# fixed bottom-anchor offset (clearing the resting ear tips with margin to
# spare) plus a defensive top clamp mirroring the left/right clamps already
# below, so this can never silently clip again even for a taller bubble.
_NUDGE_BUBBLE_BOTTOM_OFFSET = BODY_RY * 1.05

# v1.10: a distinctly more "alert" treatment for reminder-sourced nudges,
# reusing this codebase's existing low-battery-badge amber (`#FB8C00`,
# status_badge Badge.LOW_BATTERY's color) rather than inventing a new
# "urgent" color from scratch -- it already reads as "pay attention" here.
_ALERT_FILL_COLOR = QColor("#FFF3E0")
_ALERT_BORDER_COLOR = QColor("#FB8C00")
_ALERT_ICON_RESERVE = 20.0
_ALERT_POP_SECONDS = 0.22


def nudge_bubble_size(text: str, alert: bool) -> tuple[float, float]:
    """The natural (unclamped) single-line bubble size, in canvas units,
    for `text`/`alert` -- the single source of truth for this geometry,
    shared between `_draw_speech_bubble`'s actual drawing below and
    `KittenWindow._grow_for_nudge` (window.py), which needs to know how
    wide the *physical window itself* must temporarily grow to fit a long
    reply without clipping it -- see the v1.10 bugfix entry in
    DEVELOPMENT_NOTES.md for why the window has to grow at all rather than
    just repositioning the bubble within a fixed size."""
    font = QFont("Segoe UI", 9, QFont.Bold if alert else QFont.Normal)
    metrics = QFontMetricsF(font)
    padding_x, padding_y = 8.0, 5.0
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

    font = QFont("Segoe UI", 9, QFont.Bold if alert else QFont.Normal)
    painter.setFont(font)
    padding_x = 8.0
    icon_reserve = _ALERT_ICON_RESERVE if alert else 0.0
    bubble_w, bubble_h = nudge_bubble_size(text, alert)

    bubble = QRectF(0, 0, bubble_w, bubble_h)
    bubble_bottom = center.y() - _NUDGE_BUBBLE_BOTTOM_OFFSET
    bubble.moveCenter(QPointF(center.x(), bubble_bottom - bubble.height() / 2))
    # Keep the bubble from drifting past the drawable area at small sizes --
    # `canvas_half_width` is the *actual* available half-width for this
    # paint call (normally CANVAS/2, but wider once window.py has grown the
    # physical window to fit a long reply), not a fixed constant, so a long
    # message can genuinely use the extra room rather than still being
    # clamped to the original narrow bound.
    left_bound = CANVAS / 2 - canvas_half_width + 2
    right_bound = CANVAS / 2 + canvas_half_width - 2
    if bubble.left() < left_bound:
        bubble.moveLeft(left_bound)
    if bubble.right() > right_bound:
        bubble.moveRight(right_bound)
    if bubble.top() < 2:
        bubble.moveTop(2)

    # A quick "pop" grow-in for alert bubbles only, over the reminder's
    # first ~0.2s on screen -- regular nudges keep the plain opacity-only
    # fade-in unchanged, so this reads as reminder-specific emphasis, not a
    # new universal animation.
    if alert and elapsed < _ALERT_POP_SECONDS:
        scale = 0.6 + 0.4 * max(0.0, elapsed / _ALERT_POP_SECONDS)
        painter.translate(bubble.center())
        painter.scale(scale, scale)
        painter.translate(-bubble.center())

    fill = _ALERT_FILL_COLOR if alert else WHITE
    border = _ALERT_BORDER_COLOR if alert else OUTLINE_COLOR
    pen = _outline_pen(2.2 if alert else 1.6)
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
        painter.setPen(OUTLINE_COLOR)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
    else:
        painter.setPen(OUTLINE_COLOR)
        painter.drawText(bubble, Qt.AlignCenter, text)
    painter.restore()


def _draw_alarm_icon(painter: QPainter, pos: QPointF, t: float) -> None:
    """A small alarm-clock glyph shown at the left of an alert bubble --
    distinct from the star/crown/battery icons elsewhere in this file, and
    matching the clock emoji already used in `reminders.format_due_reply`.
    A quick side-to-side "ring" jitter (reusing the same sine-wiggle idiom
    as the purr-reaction ear wiggle) is the icon's own small contribution to
    reading as more attention-grabbing than a static glyph."""
    painter.save()
    ring = 6.0 * math.sin(t * 9.0)
    painter.translate(pos)
    painter.rotate(ring)
    radius = 6.5
    painter.setPen(_outline_pen(1.2))
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    # The two small "feet" that make it read as an alarm clock rather than
    # a plain clock face.
    painter.drawLine(QPointF(-4.6, -4.6), QPointF(-7.0, -7.4))
    painter.drawLine(QPointF(4.6, -4.6), QPointF(7.0, -7.4))
    # Hands, in the accent color so they stand out against the white face.
    hand_pen = _outline_pen(1.3)
    hand_pen.setColor(_ALERT_BORDER_COLOR)
    painter.setPen(hand_pen)
    painter.drawLine(QPointF(0, 0), QPointF(0, -3.6))
    painter.drawLine(QPointF(0, 0), QPointF(2.8, 1.4))
    painter.restore()


# -- seasonal accessories -----------------------------------------------------
# A small hat/icon worn on top of the head -- visually distinct from the
# badge (top-left) and streak (top-right) corner icons, since a hat reads as
# "worn" rather than "floating beside."

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
    painter.setPen(_outline_pen(1.4))
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
    painter.setPen(_outline_pen(1.2))
    painter.setBrush(QColor("#B32B3A"))
    body = QRectF(0, 0, 16.0, 15.0)
    body.moveCenter(QPointF(pos.x(), pos.y() + 3.0))
    painter.drawEllipse(body)

    # a small calyx/crown on top -- the pomegranate's signature silhouette
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#5C8A4A"))
    crown = [
        QPointF(pos.x() - 4.0, pos.y() - 3.5),
        QPointF(pos.x(), pos.y() - 10.0),
        QPointF(pos.x() + 4.0, pos.y() - 3.5),
    ]
    _draw_polygon(painter, crown)
    painter.restore()


def _draw_party_hat(painter: QPainter, pos: QPointF) -> None:
    painter.save()
    painter.setPen(_outline_pen(1.4))
    cone = QPainterPath(QPointF(pos.x() - 9.0, pos.y() + 5.0))
    cone.lineTo(QPointF(pos.x(), pos.y() - 18.0))
    cone.lineTo(QPointF(pos.x() + 9.0, pos.y() + 5.0))
    cone.closeSubpath()

    gradient = QLinearGradient(QPointF(pos.x(), pos.y() - 18.0), QPointF(pos.x(), pos.y() + 5.0))
    gradient.setColorAt(0.0, QColor("#42A5F5"))
    gradient.setColorAt(0.5, QColor("#FFEE58"))
    gradient.setColorAt(1.0, QColor("#EF5350"))
    painter.setBrush(gradient)
    painter.drawPath(cone)

    painter.setPen(Qt.NoPen)
    painter.setBrush(WHITE)
    painter.drawEllipse(QPointF(pos.x(), pos.y() - 18.0), 2.5, 2.5)
    painter.restore()


# -- high five --------------------------------------------------------------


def _draw_high_five_paw(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    wobble = 1.5 * math.sin(t * 10.0)
    paw_x = center.x() + BODY_RX * 0.85 + wobble
    paw_y = center.y() - BODY_RY * 0.75

    pen = _outline_pen(1.6)
    painter.setPen(pen)
    painter.setBrush(BODY_HIGHLIGHT)
    pad_radius = 7.5
    painter.drawEllipse(QPointF(paw_x, paw_y), pad_radius, pad_radius)

    # three small toe bumps along the top of the pad
    for dx in (-4.0, 0.0, 4.0):
        toe = QPointF(paw_x + dx, paw_y - pad_radius + 1.5)
        painter.drawEllipse(toe, 2.2, 2.2)
    painter.restore()


# -- mouse (v1.7 chase minigame) --------------------------------------------
# A separate, much simpler sprite for `mouse_window.py`'s small companion
# widget -- its own small logical canvas (mirroring `paint_kitten`'s
# canvas-plus-scale-transform pattern), no mood/state of its own, just a
# single gently-breathing pose per the spec.

MOUSE_CANVAS = 64.0
_MOUSE_CENTER = QPointF(MOUSE_CANVAS / 2, MOUSE_CANVAS / 2 + 4)
_MOUSE_BODY_COLOR = QColor("#9E9E9E")
_MOUSE_BODY_HIGHLIGHT = QColor("#BDBDBD")
_MOUSE_BODY_RX, _MOUSE_BODY_RY = 15.0, 11.0


def paint_mouse(painter: QPainter, rect: QRectF, t: float) -> None:
    """Draws the mouse (rodent) sprite for the v1.7 chase minigame: a small
    oval body, a thin curved tail, two small round ears, two dot eyes --
    exactly the elements the spec asked for, nothing more. A single gentle
    breathing animation (the same sine-wave idiom used throughout this
    codebase) is enough; it has no mood or interaction states of its own."""
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

    gradient = QRadialGradient(
        QPointF(center.x() - _MOUSE_BODY_RX * 0.35, center.y() - _MOUSE_BODY_RY * 0.5),
        _MOUSE_BODY_RX * 1.6,
    )
    gradient.setColorAt(0.0, _MOUSE_BODY_HIGHLIGHT)
    gradient.setColorAt(1.0, _MOUSE_BODY_COLOR)

    painter.setPen(_outline_pen(2.0))
    painter.setBrush(gradient)
    painter.drawEllipse(rect)
    painter.restore()


def _draw_mouse_ears(painter: QPainter, center: QPointF) -> None:
    painter.save()
    painter.setPen(_outline_pen(1.8))
    painter.setBrush(_MOUSE_BODY_HIGHLIGHT)
    ear_y = center.y() - _MOUSE_BODY_RY * 0.95
    for side in (-1, 1):
        ex = center.x() + side * _MOUSE_BODY_RX * 0.55
        painter.drawEllipse(QPointF(ex, ear_y), 6.5, 6.5)
    painter.restore()


def _draw_mouse_tail(painter: QPainter, center: QPointF) -> None:
    painter.save()
    pen = _outline_pen(1.6)
    pen.setColor(OUTLINE_COLOR)
    painter.setPen(pen)

    base = QPointF(center.x() + _MOUSE_BODY_RX * 0.8, center.y() + _MOUSE_BODY_RY * 0.3)
    c1 = QPointF(base.x() + 14, base.y() + 8)
    c2 = QPointF(base.x() + 4, base.y() + 20)
    end = QPointF(base.x() + 16, base.y() + 22)

    path = QPainterPath(base)
    path.cubicTo(c1, c2, end)
    painter.drawPath(path)
    painter.restore()


def _draw_mouse_face(painter: QPainter, center: QPointF) -> None:
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(OUTLINE_COLOR)
    eye_y = center.y() - _MOUSE_BODY_RY * 0.2
    for side in (-1, 1):
        ex = center.x() + side * _MOUSE_BODY_RX * 0.4
        painter.drawEllipse(QPointF(ex, eye_y), 1.8, 1.8)
    painter.restore()
