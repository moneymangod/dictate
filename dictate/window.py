"""Setup window: status and recent transcriptions. Dark, matching the Arch dashboard."""
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPointF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

MAX_RECENT = 20
STATES = {
    "loading": ("Loading model…", "#e9973f"),
    "ready": ("Ready", "#4caf50"),
    "listening": ("Listening", "#7c6ce0"),
    "transcribing": ("Transcribing", "#22d3c5"),
    "error": ("Error", "#fb464c"),
}

STYLE = """
#root { background: #1e1e1e; }
QLabel { color: #dcddde; font-family: 'Segoe UI'; font-size: 13px; }
#title { font-size: 20px; font-weight: 600; }
#muted, #time { color: #a1a1a1; }
#time { font-size: 12px; }
#detail { color: #fb464c; }
#section { color: #a1a1a1; font-size: 12px; font-weight: 600; letter-spacing: 1px; }
#card, #item { background: #161616; border: 1px solid #2a2a2a; border-radius: 12px; }
#pill { background: #222222; border: 1px solid #2a2a2a; border-radius: 13px; }
QPushButton { background: #2a2a2a; color: #dcddde; border: 1px solid #2a2a2a; border-radius: 8px;
              padding: 4px 12px; font-family: 'Segoe UI'; font-size: 12px; }
QPushButton:hover { background: #303030; }
QPushButton[copied="true"] { background: #7c6ce0; border-color: #7c6ce0; color: #ffffff; }
QScrollArea, #list { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #2a2a2a; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _rise_curve() -> QEasingCurve:
    curve = QEasingCurve(QEasingCurve.BezierSpline)
    curve.addCubicBezierSegment(QPointF(0.2, 0.7), QPointF(0.3, 1.0), QPointF(1.0, 1.0))
    return curve


class _Dot(QWidget):
    """Status dot that breathes (1.6 s ease-in-out, like Arch's jv-breathe)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(18, 18)
        self.color = QColor("#e9973f")
        self._value = 1.0
        self._anim = QVariantAnimation(self, startValue=0.35, endValue=0.35, duration=1600, loopCount=-1)
        self._anim.setKeyValueAt(0.5, 1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.start()

    def _on_value(self, value: float) -> None:
        self._value = value
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        halo = QColor(self.color)
        halo.setAlphaF(0.25 * self._value)
        r = 4 + 4 * self._value
        p.setBrush(halo)
        p.drawEllipse(QPointF(9, 9), r, r)
        core = QColor(self.color)
        core.setAlphaF(0.5 + 0.5 * self._value)
        p.setBrush(core)
        p.drawEllipse(QPointF(9, 9), 4, 4)


class _Item(QFrame):
    def __init__(self, text: str):
        super().__init__(objectName="item")
        self._text = text
        self._layout = row = QHBoxLayout(self)
        body = QVBoxLayout()
        body.setSpacing(4)
        body.addWidget(QLabel(datetime.now().strftime("%H:%M:%S"), objectName="time"))
        label = QLabel(text, wordWrap=True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(label)
        row.addLayout(body, 1)
        self._copy = QPushButton("Copy", cursor=Qt.PointingHandCursor)
        self._copy.clicked.connect(self._on_copy)
        row.addWidget(self._copy, 0, Qt.AlignTop)
        self._rise_in()

    def _rise_in(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=500, easingCurve=_rise_curve())

        def step(v: float) -> None:
            effect.setOpacity(v)
            offset = round(8 * (1 - v))  # slide up while keeping the item's height constant
            self._layout.setContentsMargins(14, 12 + offset, 14, 12 - offset)

        anim.valueChanged.connect(step)
        anim.finished.connect(lambda: self.setGraphicsEffect(None))
        step(0.0)
        anim.start()

    def _on_copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text)
        self._set_copied(True)
        QTimer.singleShot(1200, lambda: self._set_copied(False))

    def _set_copied(self, copied: bool) -> None:
        self._copy.setText("Copied ✓" if copied else "Copy")
        self._copy.setProperty("copied", copied)
        self._copy.style().polish(self._copy)


class MainWindow(QWidget):
    def __init__(self, icon):
        super().__init__(objectName="root")
        self.setWindowTitle("Dictate")
        self.setWindowIcon(icon)
        self.setStyleSheet(STYLE)
        self.setAttribute(Qt.WA_StyledBackground)
        self.resize(460, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(QLabel("Dictate", objectName="title"))
        header.addStretch(1)
        pill = QFrame(objectName="pill")
        pill_row = QHBoxLayout(pill)
        pill_row.setContentsMargins(6, 3, 12, 3)
        pill_row.setSpacing(4)
        self._dot = _Dot()
        self._status = QLabel()
        pill_row.addWidget(self._dot)
        pill_row.addWidget(self._status)
        header.addWidget(pill)
        root.addLayout(header)

        self._detail = QLabel(objectName="detail", wordWrap=True)
        self._detail.hide()
        root.addWidget(self._detail)

        card = QFrame(objectName="card")
        card_col = QVBoxLayout(card)
        card_col.setContentsMargins(16, 14, 16, 14)
        card_col.addWidget(QLabel("Hold <b>Right Shift</b> to dictate · release to paste"))
        card_col.addWidget(
            QLabel("Text goes into whatever textbox has focus. Speech is transcribed by Groq.", objectName="muted", wordWrap=True)
        )
        root.addWidget(card)

        root.addWidget(QLabel("RECENT TRANSCRIPTIONS", objectName="section"))
        self._empty = QLabel("Nothing yet. Hold Right Shift and speak.", objectName="muted", alignment=Qt.AlignCenter)
        root.addWidget(self._empty)
        items = QWidget(objectName="list")
        self._items = QVBoxLayout(items)
        self._items.setContentsMargins(0, 0, 4, 0)
        self._items.setSpacing(8)
        self._items.addStretch(1)
        scroll = QScrollArea(widgetResizable=True)
        scroll.setWidget(items)
        root.addWidget(scroll, 1)

        self.set_status("loading")

    def set_status(self, state: str, detail: str = "") -> None:
        text, color = STATES[state]
        self._status.setText(text)
        self._dot.color = QColor(color)
        self._dot.update()
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))

    def add_transcript(self, text: str) -> None:
        self._empty.hide()
        self._items.insertWidget(0, _Item(text))
        while self._items.count() - 1 > MAX_RECENT:  # the last entry is the stretch
            self._items.takeAt(MAX_RECENT).widget().deleteLater()

    def closeEvent(self, event) -> None:
        event.ignore()  # keep running in the tray
        self.hide()
