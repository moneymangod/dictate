"""Pastes text into the focused window via the clipboard, then restores what was on the clipboard."""
from pynput.keyboard import Controller, Key
from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

RESTORE_MS = 250
_keys = Controller()


def _snapshot(src: QMimeData) -> QMimeData:
    copy = QMimeData()
    for fmt in src.formats():
        copy.setData(fmt, src.data(fmt))
    if src.hasImage():
        copy.setImageData(src.imageData())
    return copy


def paste(text: str) -> None:
    clipboard = QGuiApplication.clipboard()
    saved = _snapshot(clipboard.mimeData())
    clipboard.setText(text)
    with _keys.pressed(Key.ctrl):
        _keys.tap("v")
    QTimer.singleShot(RESTORE_MS, lambda: clipboard.setMimeData(saved))
