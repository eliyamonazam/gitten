"""QPainter drawing code for the kitten.

Everything is drawn with primitive shapes (ellipses, triangles, painter
paths) in a fixed 128x128 logical coordinate space -- no external art
assets. `paint_kitten` is pure with respect to Qt widget state: give it a
painter, a target rect, a mood, and a monotonically increasing time in
seconds, and it draws one animated frame.
"""

from __future__ import annotations

import math

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
    turn_stage: int | None = None,
    streak: int = 0,
    focused: bool = False,
) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    scale = min(rect.width(), rect.height()) / CANVAS
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.translate(-CANVAS / 2, -CANVAS / 2)

    breathe = 1.0 + 0.018 * math.sin(t * 2.0)
    bob = 1.5 * math.sin(t * 2.0) if not dragging else 0.0
    tail_phase = math.sin(t * 1.6) * 0.5 + math.sin(t * 0.7) * 0.2
    jitter_x = 0.6 * math.sin(t * 14.0) if mood == Mood.WAITING else 0.0

    center = QPointF(CENTER.x() + jitter_x, CENTER.y() + bob)

    # "Focused" (a matching test/build process is currently running) is a
    # standalone reaction layered independently of git mood, but sulking
    # still takes precedence -- a cat mid-sulk doesn't perk up for a test run.
    show_focused = focused and turn_stage is None

    _draw_shadow(painter, center)
    _draw_tail(painter, center, tail_phase)
    _draw_ears(painter, center, breathe, perked=show_focused)
    _draw_body(painter, center, breathe)
    if turn_stage is not None:
        _draw_face_turned(painter, center, turn_stage, t)
    elif show_focused:
        _draw_focused_face(painter, center, t)
    else:
        _draw_face(painter, center, mood, t)
        urgent = badge in (Badge.LOW_BATTERY, Badge.CRITICAL_BATTERY)
        _draw_mood_overlay(painter, center, mood, t, urgent=urgent)

    if badge is not None and badge != Badge.NONE:
        _draw_status_badge(painter, center, badge, t)

    if streak >= 3:
        _draw_streak_icon(painter, center, streak, t)

    if nudge_text and nudge_opacity > 0.0:
        _draw_nudge_wave(painter, center, t)
        _draw_speech_bubble(painter, center, nudge_text, nudge_opacity)

    painter.restore()


def _draw_shadow(painter: QPainter, center: QPointF) -> None:
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(SHADOW_COLOR)
    shadow_rect = QRectF(0, 0, BODY_RX * 2.1, 10.0)
    shadow_rect.moveCenter(QPointF(center.x(), center.y() + BODY_RY + 8))
    painter.drawEllipse(shadow_rect)
    painter.restore()


def _draw_tail(painter: QPainter, center: QPointF, phase: float) -> None:
    painter.save()
    pen = _outline_pen(9.0)
    pen.setColor(BODY_COLOR)
    painter.setPen(pen)

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


def _draw_ears(painter: QPainter, center: QPointF, breathe: float, perked: bool = False) -> None:
    painter.save()
    painter.setPen(_outline_pen())
    # "Perked" (focus reaction): ears stand taller and lean in toward the
    # center, an alert/attentive posture, instead of the normal relaxed angle.
    height_scale = 1.3 if perked else 1.0
    lean = 0.5 if perked else 1.0
    for side in (-1, 1):
        ex = center.x() + side * BODY_RX * 0.62
        ey = center.y() - BODY_RY * 0.82
        outer = [
            QPointF(ex - 13 * side, ey + 6),
            QPointF(ex + 4 * side * lean, ey - 24 * breathe * height_scale),
            QPointF(ex + 15 * side, ey + 10),
        ]
        painter.setBrush(BODY_COLOR)
        _draw_polygon(painter, outer)

        inner = [
            QPointF(ex - 6 * side, ey + 3),
            QPointF(ex + 3 * side * lean, ey - 12 * breathe * height_scale),
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


def _draw_body(painter: QPainter, center: QPointF, breathe: float) -> None:
    painter.save()
    rect = QRectF(0, 0, BODY_RX * 2, BODY_RY * 2 * breathe)
    rect.moveCenter(center)

    gradient = QRadialGradient(
        QPointF(center.x() - BODY_RX * 0.35, center.y() - BODY_RY * 0.5),
        BODY_RX * 1.6,
    )
    gradient.setColorAt(0.0, BODY_HIGHLIGHT)
    gradient.setColorAt(1.0, BODY_COLOR)

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


def _draw_zzz(painter: QPainter, center: QPointF, t: float) -> None:
    painter.save()
    font = QFont("Comic Sans MS", 10)
    font.setItalic(True)
    painter.setFont(font)

    top = QPointF(center.x() + BODY_RX * 0.5, center.y() - BODY_RY * 1.35)
    letters = "zzz"
    for i, ch in enumerate(letters):
        cycle = 3.0
        phase = (t * 0.5 + i * 0.33) % 1.0
        rise = phase * 16.0
        alpha = int(220 * (1.0 - phase))
        size = 7 + i * 2
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


def _draw_speech_bubble(painter: QPainter, center: QPointF, text: str, opacity: float) -> None:
    painter.save()
    painter.setOpacity(max(0.0, min(1.0, opacity)))

    font = QFont("Segoe UI", 9)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    padding_x, padding_y = 8.0, 5.0
    tw = metrics.horizontalAdvance(text)
    th = metrics.height()

    bubble = QRectF(0, 0, tw + padding_x * 2, th + padding_y * 2)
    bubble.moveCenter(QPointF(center.x(), center.y() - BODY_RY * 1.9 - bubble.height() / 2))
    # Keep the bubble from drifting past the drawing canvas at small sizes.
    if bubble.left() < 2:
        bubble.moveLeft(2)
    if bubble.right() > CANVAS - 2:
        bubble.moveRight(CANVAS - 2)

    painter.setPen(_outline_pen(1.6))
    painter.setBrush(WHITE)
    painter.drawRoundedRect(bubble, 6.0, 6.0)

    tail = QPainterPath(QPointF(center.x() - 4, bubble.bottom() - 1))
    tail.lineTo(QPointF(center.x() + 4, bubble.bottom() - 1))
    tail.lineTo(QPointF(center.x(), bubble.bottom() + 7))
    tail.closeSubpath()
    painter.drawPath(tail)

    painter.setPen(OUTLINE_COLOR)
    painter.drawText(bubble, Qt.AlignCenter, text)
    painter.restore()
