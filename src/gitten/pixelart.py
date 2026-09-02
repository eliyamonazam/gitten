"""Generic pixel-art rendering engine (v1.16), Part 0 of
`GITTEN_V1_16_SPEC.md` -- the shared technical foundation every pose in
`sprite.py` builds on, the same "shared infrastructure built once, reused
everywhere" discipline `theme.py` and `particles.ParticleSystem` already
established for their own concerns.

A pixel-art **frame** is a small, fixed-size grid: a tuple of equal-length
strings, one character per logical pixel. `.` means transparent; any other
character is a key into a small per-sprite **palette** (a plain
`dict[str, str]` mapping a character to a hex color) -- roughly 4-6 colors
per sprite. This is a standard, compact way to write pixel art directly in
code (a 2D grid of color keys); it isn't tied to any specific existing
project's own art format, tooling, or palette.

**Rendering technique**: `render_frame` draws a frame to a small off-screen
`QImage` at its own logical grid resolution (one image pixel per grid
cell), using flat, single-color fills -- no gradients, no anti-aliasing.
`draw_pixel_image` then scales that image up to fill an arbitrary on-screen
rect using **nearest-neighbor scaling** (`Qt.FastTransformation`, not the
smooth default) -- this is what actually produces crisp, hard pixel edges
instead of a blurry upscaled blob, and it's applied on top of whatever
outer `QPainter` transform (window.py's canvas-unit scale, mood-driven
translate/rotate) is already active, since it also explicitly turns off
the painter's own smooth-pixmap-transform hint for this one draw call.

Verified in isolation (a placeholder checkerboard grid, scaled up and
sampled pixel-by-pixel to confirm every output pixel is an exact palette
color with no blended/interpolated colors anywhere) before any real pose
was built on top of it -- see `DEVELOPMENT_NOTES.md`'s v1.16 entry, Part 0.

**Frame timing**: real pixel-art characters typically animate via a small,
fixed number of discrete frames swapped on a timer (like an old sprite
sheet), not continuous interpolation. `frame_index` below is the one
shared convention every pose's own discrete animation (idle's breathe/
blink, purr's squint, a nervous side-glance, ...) reuses, rather than each
pose inventing its own timer math. Continuous *position* animation (a
walk, a drag, a particle's drift/fade, a badge's pulse/bob) is a different
concern entirely and isn't part of this module -- see
`GITTEN_V1_16_SPEC.md`'s explicit "what does NOT need to change" note.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

Frame = tuple[str, ...]
Palette = dict[str, str]

# Rendered frames are small and the (frame, palette) space actually used is
# small too (a handful of poses x at most a couple of palette variants each,
# e.g. day/night) -- caching here means a steady-state paint loop never
# rebuilds the same QImage twice. Callers that build a palette with a
# continuously-varying value (e.g. a pulsing badge's alpha) round that value
# first specifically so this cache doesn't grow without bound -- see
# sprite.py's own badge/streak-icon code for that rounding.
_image_cache: dict[tuple[Frame, tuple[tuple[str, str], ...]], QImage] = {}


def render_frame(frame: Frame, palette: Palette) -> QImage:
    """Render one grid `frame` to a QImage at its own logical pixel size --
    one image pixel per grid cell, flat-filled, fully opaque or fully
    transparent (no anti-aliasing anywhere in this step)."""
    key = (frame, tuple(sorted(palette.items())))
    cached = _image_cache.get(key)
    if cached is not None:
        return cached
    height = len(frame)
    width = len(frame[0]) if height else 0
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    for row_index, row in enumerate(frame):
        for col_index, ch in enumerate(row):
            if ch != ".":
                image.setPixelColor(col_index, row_index, QColor(palette[ch]))
    _image_cache[key] = image
    return image


def draw_pixel_image(painter: QPainter, image: QImage, rect: QRectF) -> None:
    """Draw `image` scaled to fill `rect`, always via nearest-neighbor
    (point-sampled) scaling -- never smoothed/interpolated, regardless of
    what render hints the caller's own painter already has set. Two things
    make that true together: scaling the `QPixmap` itself with the explicit
    `Qt.FastTransformation` flag, *and* turning off this painter's own
    smooth-pixmap-transform hint for the `drawPixmap` call below (a plain
    `drawImage` scale would otherwise still respect the painter's own
    smoothing hint even if the source data were pre-scaled crisply)."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
    target_w = max(1, round(rect.width()))
    target_h = max(1, round(rect.height()))
    pixmap = QPixmap.fromImage(image).scaled(
        target_w, target_h, Qt.IgnoreAspectRatio, Qt.FastTransformation
    )
    painter.drawPixmap(QPointF(rect.left(), rect.top()), pixmap)
    painter.restore()


def frame_index(t: float, num_frames: int, frame_seconds: float) -> int:
    """The one shared discrete-animation convention: cycle through
    `num_frames` fixed frame indices, holding each for `frame_seconds`
    before advancing -- an old sprite sheet's own timing model, not a
    continuous interpolation. `t` is the same monotonically-increasing
    seconds clock every other animated element in this codebase already
    takes as a plain argument (see `sprite.paint_kitten`'s own `t`)."""
    if num_frames <= 1:
        return 0
    return int(t / frame_seconds) % num_frames
