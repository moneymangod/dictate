"""Screen-edge glow: four thin, click-through, always-on-top strips that never take focus.
The animation timer only runs while the glow is visible."""
import ctypes
import math
import time
from ctypes import wintypes

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

PALETTE = [QColor("#6d6af6"), QColor("#3d8bff"), QColor("#a855f7"), QColor("#22d3c5")]  # Arch glow colors
RED = QColor("#fb464c")
WHITE = QColor("#ffffff")
STRIP = 44  # Strip size in px = maximum glow thickness.
STOPS = 32  # Color stops along each strip.

_user32 = ctypes.windll.user32
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def _foreground_screen():
    """The screen showing the foreground window, falling back to the primary screen."""
    info = _MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(info)
    monitor = _user32.MonitorFromWindow(_user32.GetForegroundWindow(), 2)  # MONITOR_DEFAULTTONEAREST
    if monitor and _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        for screen in QGuiApplication.screens():
            top_left = screen.geometry().topLeft()  # Qt keeps native coordinates for a screen's origin.
            if screen.name() == info.szDevice or (top_left.x(), top_left.y()) == (info.rcMonitor.left, info.rcMonitor.top):
                return screen
    return QGuiApplication.primaryScreen()


def _mix(a: QColor, b: QColor, f: float) -> QColor:
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * f, a.greenF() + (b.greenF() - a.greenF()) * f, a.blueF() + (b.blueF() - a.blueF()) * f)


def _palette_at(u: float) -> QColor:
    x = (u % 1.0) * len(PALETTE)
    i = int(x)
    return _mix(PALETTE[i], PALETTE[(i + 1) % len(PALETTE)], x - i)


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
        self.glow.paint(self)


class EdgeGlow:
    def __init__(self, level_fn):
        self._level_fn = level_fn  # 0..1 mic level while listening
        self._strips = [_Strip(self, side) for side in ("top", "right", "bottom", "left")]
        self._timer = QTimer(interval=16)
        self._timer.timeout.connect(self._tick)
        self._state = "hidden"
        self._since = self._last = time.monotonic()
        self._alpha = self._level = self._band = self._white = 0.0
        self._thick = 0.3
        self._red = False
        self._w = self._h = 1

    # States ---------------------------------------------------------------

    def listen(self) -> None:
        self._show()
        self._set("listening")

    def transcribing(self) -> None:
        if self._state != "hidden":
            self._set("transcribing")

    def done(self) -> None:
        if self._state not in ("hidden", "error"):
            self._set("done")

    def discard(self) -> None:
        if self._state not in ("hidden", "error"):  # never cut an error pulse short
            self._set("discard")

    def error(self) -> None:
        self._show()
        self._set("error")

    def _set(self, state: str) -> None:
        self._state = state
        self._since = time.monotonic()
        self._red = state == "error"

    def _show(self) -> None:
        if self._state == "hidden":
            g = _foreground_screen().geometry()
            self._w, self._h = g.width(), g.height()
            s = STRIP
            self._strips[0].setGeometry(g.x(), g.y(), g.width(), s)
            self._strips[1].setGeometry(g.x() + g.width() - s, g.y() + s, s, g.height() - 2 * s)
            self._strips[2].setGeometry(g.x(), g.y() + g.height() - s, g.width(), s)
            self._strips[3].setGeometry(g.x(), g.y() + s, s, g.height() - 2 * s)
            self._alpha = self._level = self._band = self._white = 0.0
            self._last = time.monotonic()
            for strip in self._strips:
                strip.show()
            self._timer.start()

    def _hide(self) -> None:
        self._state = "hidden"
        self._timer.stop()
        for strip in self._strips:
            strip.hide()

    # Animation ------------------------------------------------------------

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(0.05, now - self._last), now
        t = now - self._since
        state = self._state
        target_level = self._level_fn() if state == "listening" else 0.0
        self._level += (target_level - self._level) * min(1.0, dt * 14)
        band_target, self._white = 0.0, 0.0

        if state == "listening":
            self._alpha = min(1.0, self._alpha + dt / 0.1)  # ~100 ms fade-in
            self._thick = 0.3 + 0.7 * self._level
        elif state == "transcribing":
            self._alpha += (0.9 - self._alpha) * min(1.0, dt * 8)
            self._thick = 0.45 + 0.08 * math.sin(t * 5)
            band_target = 1.0
        elif state == "done":
            self._white = max(0.0, 1.0 - t / 0.2)
            self._thick = 0.7 + 0.3 * self._white
            self._alpha = 1.0 if t < 0.08 else max(0.0, self._alpha - dt / 0.3)  # flash, then ~300 ms fade
        elif state == "discard":
            self._alpha = max(0.0, self._alpha - dt / 0.25)
        elif state == "error":
            self._alpha = abs(math.sin(math.pi * t / 0.35)) if t < 0.7 else 0.0  # two red pulses
            self._thick = 0.8
        self._band += (band_target - self._band) * min(1.0, dt * 10)

        if state in ("done", "discard", "error") and self._alpha <= 0.0 and t > 0.05:
            self._hide()
            return
        for strip in self._strips:
            strip.update()

    def _color_at(self, s: float, now: float) -> QColor:
        """Glow color at perimeter position s (0..1, clockwise from the top-left corner)."""
        if self._red:
            color, strength = QColor(RED), 1.0
        else:
            color = _palette_at(s + now * 0.08)
            head = (now - self._since) * 0.9  # the transcribing shimmer travels around the screen
            d = (s - head) % 1.0
            boost = math.exp(-((min(d, 1.0 - d) / 0.06) ** 2)) * self._band
            color = _mix(color, WHITE, min(1.0, self._white * 0.7 + boost * 0.55))
            strength = 1.0 - 0.55 * self._band + 0.55 * boost  # dimmer base, bright traveling band
        color.setAlphaF(max(0.0, min(1.0, self._alpha * strength)))
        return color

    def paint(self, strip: _Strip) -> None:
        w, h = strip.width(), strip.height()
        if w <= 0 or h <= 0:
            return
        W, H, s = self._w, self._h, STRIP
        perimeter = 2 * (W + H)
        now = time.monotonic()
        horizontal = strip.side in ("top", "bottom")

        along = QLinearGradient(0, 0, w, 0) if horizontal else QLinearGradient(0, 0, 0, h)
        for k in range(STOPS + 1):
            f = k / STOPS
            if strip.side == "top":
                pos = f * W
            elif strip.side == "right":
                pos = W + s + f * (H - 2 * s)
            elif strip.side == "bottom":
                pos = W + H + (W - f * W)
            else:
                pos = 2 * W + H + (H - (s + f * (H - 2 * s)))
            along.setColorAt(f, self._color_at(pos / perimeter, now))

        thick = max(2.0, self._thick * STRIP)
        start, end = {
            "top": (QPointF(0, 0), QPointF(0, thick)),
            "bottom": (QPointF(0, h), QPointF(0, h - thick)),
            "left": (QPointF(0, 0), QPointF(thick, 0)),
            "right": (QPointF(w, 0), QPointF(w - thick, 0)),
        }[strip.side]
        fade = QLinearGradient(start, end)
        fade.setColorAt(0.0, QColor(0, 0, 0, 255))
        fade.setColorAt(0.3, QColor(0, 0, 0, 120))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))

        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.fillRect(img.rect(), along)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.fillRect(img.rect(), fade)
        p.end()

        painter = QPainter(strip)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawImage(0, 0, img)
        painter.end()
