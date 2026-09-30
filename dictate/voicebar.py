"""A small pill at the bottom of the screen: its bars dance with your voice while you talk and roll like a
wave while the text is being transcribed. Click-through and never takes focus, like the edge glow."""
import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .overlay import PALETTE, active_screen

BARS = 9
BAR_W, GAP, PAD = 4, 5, 22
WIDTH, HEIGHT = 2 * PAD + BARS * BAR_W + (BARS - 1) * GAP, 44
LOW, HIGH = 4.0, 26.0  # bar heights in px
LIFT = 28  # px between the pill and the bottom of the usable screen
SLIDE = 12  # px the pill rises while fading in
BELL = [math.exp(-(((i - (BARS - 1) / 2) / 3.2) ** 2)) for i in range(BARS)]  # middle bars move most


def _color(u: float) -> QColor:
    """A point along the Arch glow colors, 0..1."""
    x = u * (len(PALETTE) - 1)
    i = min(int(x), len(PALETTE) - 2)
    r, g, b = (PALETTE[i] * (1 - (x - i)) + PALETTE[i + 1] * (x - i)) * 255
    return QColor(int(r), int(g), int(b))


class VoiceBar(QWidget):
    def __init__(self, level_fn):
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
        self.resize(WIDTH, HEIGHT)
        self._level_fn = level_fn  # 0..1 mic level
        self._state = "hidden"  # hidden | listening | transcribing | leaving
        self._alpha = 0.0
        self._level = 0.0
        self._heights = [LOW] * BARS
        self._home = (0, 0)  # where the pill rests
        self._last = time.monotonic()
        self._timer = QTimer(interval=16)
        self._timer.timeout.connect(lambda: self.advance(time.monotonic()))

    # States ---------------------------------------------------------------

    def listen(self) -> None:
        if self._state == "hidden":
            area = active_screen().availableGeometry()  # excludes the taskbar
            self._home = (area.center().x() - WIDTH // 2, area.bottom() - LIFT - HEIGHT)
            self._alpha, self._level, self._heights = 0.0, 0.0, [LOW] * BARS
            self._last = time.monotonic()
            self.move(self._home[0], self._home[1] + SLIDE)
            self.show()
            self._timer.start()
        self._state = "listening"

    def transcribing(self) -> None:
        if self._state != "hidden":
            self._state = "transcribing"

    def dismiss(self) -> None:
        if self._state != "hidden":
            self._state = "leaving"

    # Animation ------------------------------------------------------------

    def advance(self, now: float) -> None:
        dt, self._last = min(0.05, max(0.0, now - self._last)), now
        if self._state == "leaving":
            self._alpha = max(0.0, self._alpha - dt / 0.22)
            if self._alpha <= 0.0:
                self._state = "hidden"
                self._timer.stop()
                self.hide()
                return
        else:
            self._alpha = min(1.0, self._alpha + dt / 0.18)

        level = self._level_fn() if self._state == "listening" else 0.0
        self._level += (level - self._level) * min(1.0, dt * (25 if level > self._level else 8))  # like a VU meter
        for i in range(BARS):
            if self._state == "transcribing":
                target = LOW + (HIGH - LOW) * 0.5 * (0.5 + 0.5 * math.sin(now * 5 - i * 0.75))
            else:
                loud = max(self._level ** 0.6, 0.08)  # never fully flat while listening
                target = LOW + (HIGH - LOW) * loud * BELL[i] * (0.6 + 0.4 * (0.5 + 0.5 * math.sin(now * 7 + i * 1.3)))
            self._heights[i] += (target - self._heights[i]) * min(1.0, dt * (30 if target > self._heights[i] else 12))
        eased = 1 - (1 - self._alpha) ** 3
        self.move(self._home[0], round(self._home[1] + SLIDE * (1 - eased)))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._alpha)
        pill = QRectF(0.5, 0.5, WIDTH - 1, HEIGHT - 1)
        p.setBrush(QColor(24, 24, 27, 232))
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.drawRoundedRect(pill, HEIGHT / 2, HEIGHT / 2)
        p.setPen(Qt.NoPen)
        for i, height in enumerate(self._heights):
            p.setBrush(_color(i / (BARS - 1)))
            x = PAD + i * (BAR_W + GAP)
            p.drawRoundedRect(QRectF(x, (HEIGHT - height) / 2, BAR_W, height), BAR_W / 2, BAR_W / 2)
        p.end()

