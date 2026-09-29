"""Focus glow: four click-through, always-on-top strips forming a frame around a rectangle, the
focused textbox or, failing that, the active window. They never take focus.

Each frame is rendered with numpy at half resolution (the glow is soft, so it upscales cleanly):
a thin bright rim on the rectangle's border plus a colored bloom around it. The rim draws itself on
from the top edge, the bloom follows your voice in uneven waves and sends out a ripple on each loud
syllable, two comets chase around the border while transcribing, and a shockwave marks the paste.
The animation timer only runs while the glow is visible."""
import math
import time
from typing import NamedTuple

import numpy as np
from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

from .target import MIN_SIZE, foreground_rect

PALETTE = np.array([[0x6D, 0x6A, 0xF6], [0x3D, 0x8B, 0xFF], [0xA8, 0x55, 0xF7], [0x22, 0xD3, 0xC5]], np.float32) / 255  # Arch glow colors
RED = np.array([0xFB, 0x46, 0x4C], np.float32) / 255
CYAN = np.array([0x22, 0xD3, 0xC5], np.float32) / 255
SCALE = 0.5  # Render resolution relative to screen pixels.
LUT = 1024  # Perimeter samples; per-frame shading is computed on these, then looked up per pixel.
SIDES = ("top", "right", "bottom", "left")
DRAW_ON = 0.6  # The rim's draw-on reveal reaches this distance (in perimeters) from the top edge's middle: all of it.
RIPPLE_LEVEL, RIPPLE_GAP = 0.3, 0.3  # Voice level and minimum seconds between ripples.


class Ripple(NamedTuple):
    born: float
    color: object  # BGR-ordered premultiplied pixel, or None to use the border's own colors
    life: float  # seconds
    strength: float


class Look(NamedTuple):
    out: int  # px the frame reaches outside the rectangle
    inn: int  # px it reaches inside
    inner_scale: float  # how much faster the glow falls off inside than outside
    radius: float  # corner radius of the rectangle
    glow: float  # base bloom depth in px


# A halo around a textbox that leaves the text itself alone.
TEXTBOX = Look(out=84, inn=10, inner_scale=6.0, radius=6.0, glow=13.0)
# Glow inward from the window's edges, as it always has.
WINDOW = Look(out=0, inn=112, inner_scale=1.0, radius=0.0, glow=26.0)


def _logical_rect(rect: tuple[int, int, int, int]) -> QRect:
    """Physical screen pixels to Qt's coordinates, clipped to the screen the rectangle is on."""
    left, top, right, bottom = rect
    cx, cy = (left + right) // 2, (top + bottom) // 2

    def native(s):
        g, dpr = s.geometry(), s.devicePixelRatio()
        return QRect(g.topLeft(), QSize(round(g.width() * dpr), round(g.height() * dpr)))

    screen = next((s for s in QGuiApplication.screens() if native(s).contains(cx, cy)), QGuiApplication.primaryScreen())
    g, dpr = screen.geometry(), screen.devicePixelRatio()  # Qt keeps native coordinates for a screen's origin.
    o = g.topLeft()
    logical = QRect(round(o.x() + (left - o.x()) / dpr), round(o.y() + (top - o.y()) / dpr), round((right - left) / dpr), round((bottom - top) / dpr))
    return logical.intersected(g)


def _frame(w: int, h: int, look: Look) -> dict[str, QRect]:
    """The four strips around a w x h rectangle, relative to its top-left. Top and bottom own the corners."""
    o, i = look.out, max(1, min(look.inn, w // 2, h // 2))
    return {
        "top": QRect(-o, -o, w + 2 * o, o + i),
        "right": QRect(w - i, i, i + o, h - 2 * i),
        "bottom": QRect(-o, h - i, w + 2 * o, i + o),
        "left": QRect(-o, i, o + i, h - 2 * i),
    }


class _Field:
    """Per-pixel constants of one strip: squared distance to the rectangle's border (inside counted
    stronger), the thin rim on the border, and the LUT index of the nearest border point's position
    along the perimeter (0..1, clockwise from the top-left corner)."""

    def __init__(self, strip: QRect, w: int, h: int, look: Look):
        nx, ny = max(1, math.ceil(strip.width() * SCALE)), max(1, math.ceil(strip.height() * SCALE))
        X, Y = np.meshgrid(strip.x() + (np.arange(nx, dtype=np.float32) + 0.5) / SCALE, strip.y() + (np.arange(ny, dtype=np.float32) + 0.5) / SCALE)
        r = min(look.radius, w / 2, h / 2)  # Signed distance to a rounded rectangle: negative inside.
        qx, qy = np.abs(X - w / 2) - (w / 2 - r), np.abs(Y - h / 2) - (h / 2 - r)
        sd = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
        self.d2 = (np.where(sd > 0, sd, -sd * look.inner_scale) ** 2).astype(np.float32)

        sides = np.stack([Y, w - X, h - Y, X])  # Distance to the top, right, bottom and left side lines.
        cx, cy = np.clip(X, 0, w), np.clip(Y, 0, h)
        along = np.choose(np.abs(sides).argmin(axis=0), [cx, w + cy, w + h + (w - cx), 2 * w + h + (h - cy)]) / (2 * (w + h))
        self.idx = np.minimum((along * LUT).astype(np.int32), LUT - 1)
        self.shape = X.shape

        # The rim is a ~2 px bright line on the border; only the few pixels it reaches are shaded for it.
        rim = np.exp(-(sd**2) / 4.0).ravel()
        self.rim_at = np.flatnonzero(rim > 0.004)
        self.rim = rim[self.rim_at].astype(np.float32)[:, None]
        self.rim_idx = self.idx.ravel()[self.rim_at]
        # Distance from the border on the side the glow spreads to (ripples travel that way); far away on the other.
        self.reach = np.where((sd > 0) == (look.out > 0), np.abs(sd), 1e3).astype(np.float32)


class _Strip(QWidget):
    def __init__(self, glow: "EdgeGlow", side: str):
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.glow = glow
        self.side = side

    def paintEvent(self, _event) -> None:
        image = self.glow.images.get(self.side)
        if image is None:
            return
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(self.rect(), image)
        p.end()


class EdgeGlow:
    def __init__(self, level_fn):
        self._level_fn = level_fn  # 0..1 mic level while listening
        self._strips = {side: _Strip(self, side) for side in SIDES}
        self._timer = QTimer(interval=16)
        self._timer.timeout.connect(lambda: self.advance(time.monotonic()))
        self._state = "hidden"
        self._look = WINDOW
        self._max_depth = 1.0
        self._next = None  # Textbox found after the glow started around the window.
        self._ripples: list[Ripple] = []
        self._rippled_at = 0.0
        self._origin = 0.0  # Perimeter position of the top edge's middle, where the draw-on starts.
        self._fields: dict[str, _Field] = {}
        self._along = (np.arange(LUT, dtype=np.float32) + 0.5) / LUT
        self._buffers: dict[str, np.ndarray] = {}
        self.images: dict[str, QImage] = {}
        self._since = self._last = time.monotonic()
        self._reset()

    def _reset(self) -> None:
        # Blooms in from the border: starts invisible and pulled in tight.
        self._alpha, self._spread, self._level = 0.0, 0.2, 0.0
        self._band = self._head = self._tint = self._reveal = 0.0
        self._ripples = []
        self._tint_color = CYAN

    # States ---------------------------------------------------------------

    def listen(self, rect=None) -> None:
        """Fades in around `rect` (the focused textbox, in physical screen pixels) or the active window."""
        self._show(rect)
        self._set("listening")

    def retarget(self, rect) -> None:
        """Moves a glow that started around the window onto the textbox found afterwards."""
        if self._state == "listening":
            self._next = rect

    def transcribing(self) -> None:
        if self._state != "hidden":
            self._set("transcribing")

    def done(self) -> None:
        if self._state not in ("hidden", "error"):
            self._set("done")
            self._ripples.append(Ripple(self._last, np.array([CYAN[2], CYAN[1], CYAN[0], 1.0], np.float32), 0.6, 1.4))

    def discard(self) -> None:
        if self._state not in ("hidden", "error"):  # never cut an error pulse short
            self._set("discard")

    def error(self) -> None:
        self._show(None)
        self._set("error")

    def _set(self, state: str) -> None:
        self._state = state
        self._next = None
        self._since = time.monotonic()

    def _show(self, rect) -> None:
        if self._state != "hidden":
            return
        self._place(rect)
        self._reset()
        self._last = time.monotonic()
        for strip in self._strips.values():
            strip.show()
        self._timer.start()

    def _place(self, rect) -> None:
        """Lays the frame out around a textbox, or around the active window when there's none."""
        target = _logical_rect(rect or foreground_rect())
        look = TEXTBOX if rect and min(target.width(), target.height()) >= MIN_SIZE else WINDOW
        self._look, self._max_depth = look, max(look.out, look.inn) / 2.8  # Keeps the bloom inside its strips.
        w, h = target.width(), target.height()
        self._origin = (w / 2) / (2 * (w + h))
        self._reveal = 0.0
        frame = _frame(w, h, look)
        self._fields = {side: _Field(strip, w, h, look) for side, strip in frame.items()}
        for side, strip in frame.items():
            self._strips[side].setGeometry(strip.translated(target.topLeft()))

    def _hide(self) -> None:
        self._state = "hidden"
        self._timer.stop()
        for strip in self._strips.values():
            strip.hide()

    # Animation ------------------------------------------------------------

    def advance(self, now: float) -> None:
        """Steps the animation to `now` and renders a frame."""
        dt, self._last = min(0.05, max(0.0, now - self._last)), now
        t = now - self._since
        state = self._state

        def ease(value: float, target: float, rate: float) -> float:
            return value + (target - value) * min(1.0, dt * rate)

        # Fast attack, slower release, like a VU meter.
        level = self._level_fn() if state == "listening" else 0.0
        self._reveal = min(DRAW_ON, self._reveal + dt * 1.4)
        if level > RIPPLE_LEVEL and now - self._rippled_at > RIPPLE_GAP and self._alpha > 0.5:
            self._rippled_at = now
            self._ripples.append(Ripple(now, None, 0.85, 1.5 * level))
        self._ripples = [rp for rp in self._ripples if now - rp.born < rp.life]
        self._level = ease(self._level, level, 22 if level > self._level else 5)

        if state == "listening":
            if self._next:  # Crossfade onto the textbox found after the glow started around the window.
                self._alpha = max(0.0, self._alpha - dt / 0.06)
                if self._alpha <= 0.02:
                    self._place(self._next)
                    self._next = None
            else:
                self._alpha = min(1.0, self._alpha + dt / 0.12)
            self._spread = ease(self._spread, 1.0, 10)
            self._band, self._tint = ease(self._band, 0.0, 8), ease(self._tint, 0.0, 10)
        elif state == "transcribing":
            self._alpha = ease(self._alpha, 1.0, 8)
            self._spread = ease(self._spread, 0.55, 6)
            self._band = ease(self._band, 1.0, 6)
            self._head = (self._head + dt * 0.55) % 1.0
        elif state == "done":
            # Swells into bright cyan, then retracts into the border while fading.
            burst = t < 0.14
            self._tint_color = CYAN
            self._tint = ease(self._tint, 1.0 if burst else 0.6, 30 if burst else 4)
            self._spread = ease(self._spread, 1.6 if burst else 0.1, 16 if burst else 5)
            self._band = ease(self._band, 0.0, 12)
            self._alpha = 1.0 if burst else max(0.0, self._alpha - dt / 0.4)
        elif state == "discard":
            self._alpha = max(0.0, self._alpha - dt / 0.22)
            self._spread = ease(self._spread, 0.1, 8)
            self._band = ease(self._band, 0.0, 12)
        elif state == "error":
            self._tint_color = RED
            self._tint = ease(self._tint, 1.0, 25)
            self._band = ease(self._band, 0.0, 12)
            pulse = abs(math.sin(math.pi * t / 0.3)) if t < 0.6 else 0.0  # two red pulses
            self._spread = 0.7 + 0.6 * pulse
            self._alpha = 0.35 + 0.65 * pulse if t < 0.6 else max(0.0, self._alpha - dt / 0.3)

        if state in ("done", "discard", "error") and self._alpha <= 0.0 and t > 0.05:
            self._hide()
            return
        self._render(now)
        for strip in self._strips.values():
            strip.update()

    def _render(self, now: float) -> None:
        # Shade the perimeter once (LUT samples), then look it up per pixel.
        a = self._along
        breath = 0.08 + 0.06 * math.sin(2 * math.pi * now / 1.8)  # keeps the glow alive in pauses
        energy = max(self._level, breath) if self._state == "listening" else self._level

        # Colors drift slowly around the border.
        u = (a + now * 0.1) % 1.0 * len(PALETTE)
        i = u.astype(np.int32)
        f = (u - i)[:, None]
        color = PALETTE[i] * (1 - f) + PALETTE[(i + 1) % len(PALETTE)] * f

        # Voice pushes the bloom outward in uneven, travelling waves.
        wave = 0.6 * np.sin(2 * np.pi * (3 * a - 0.3 * now)) + 0.4 * np.sin(2 * np.pi * (7 * a + 0.5 * now))
        depth = self._look.glow * self._spread * (0.55 + 1.0 * energy + 0.4 * energy * wave)

        # Two comets with sharp heads and fading tails chase around the border while transcribing.
        comet = np.zeros_like(a)
        if self._band > 0.01:
            for head in (self._head, self._head + 0.5):
                behind = (head - a) % 1.0
                comet += np.exp(-behind / 0.1) + np.exp(-(((1.0 - behind) / 0.02) ** 2))  # tail + soft head
            comet *= self._band
        # The rim draws itself on from the top edge's middle, both ways round, with a hot leading edge.
        away = np.abs(a - self._origin)
        away = np.minimum(away, 1.0 - away)
        if self._reveal < DRAW_ON:
            comet = comet + 1.3 * np.exp(-(((self._reveal - away) / 0.03) ** 2))
        drawn = np.clip((self._reveal - away) / 0.1, 0.0, 1.0)
        depth = np.clip(depth * (1 + 1.2 * comet), 1.0, self._max_depth)
        strength = (1 - 0.45 * self._band + 1.1 * comet) * drawn

        color = color * (1 - 0.35 * comet[:, None]) + 0.35 * comet[:, None]  # comet heads run hot
        if self._tint > 0.001:
            color = color * (1 - self._tint) + self._tint_color * self._tint
        inv_depth2 = (1.0 / depth**2).astype(np.float32)
        # Premultiplied BGRA (QImage.Format_ARGB32_Premultiplied byte order) per perimeter sample, 0..255.
        bloom_lut = np.empty((LUT, 4), np.float32)
        bloom_lut[:, 2::-1], bloom_lut[:, 3] = color, 1.0
        bloom_lut *= (255 * 0.9 * self._alpha * strength)[:, None]
        rim_lut = np.empty((LUT, 4), np.float32)
        rim_lut[:, 2::-1], rim_lut[:, 3] = color * 0.7 + 0.3, 1.0  # tinted, not white: stays visible on light apps
        rim_lut *= (255 * 0.9 * self._alpha * np.minimum(strength, 1.0) * (1 + 0.6 * comet))[:, None]

        reach = 0.85 * max(self._look.out, self._look.inn)
        rings = []
        for rp in self._ripples:  # Each ripple is a thin ring that travels away from the border and fades.
            x = (now - rp.born) / rp.life
            fade = rp.strength * (1 - x) ** 1.5
            paint = rp.color * (255 * self._alpha * fade) if rp.color is not None else rim_lut * fade
            rings.append((reach * (1 - (1 - x) ** 2), 2.5 + 5 * x, paint))

        for side, fd in self._fields.items():
            px = bloom_lut[fd.idx]
            px *= np.exp(-fd.d2 * inv_depth2[fd.idx])[..., None]
            for radius, sigma, paint in rings:
                ring = np.exp(-(((fd.reach - radius) / sigma) ** 2))[..., None]
                px += ring * (paint[fd.idx] if paint.ndim == 2 else paint)
            flat = px.reshape(-1, 4)
            flat[fd.rim_at] += rim_lut[fd.rim_idx] * fd.rim
            np.minimum(px, 255, out=px)  # color <= 1, so clipped values stay valid premultiplied
            buf = px.astype(np.uint8)
            self._buffers[side] = buf  # keeps the memory alive for the QImage
            h, w = fd.shape
            self.images[side] = QImage(buf.data, w, h, 4 * w, QImage.Format_ARGB32_Premultiplied)
