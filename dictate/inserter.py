"""Pastes text into the focused window via the clipboard, then restores what was on the clipboard.
Windows and X11 use Qt's clipboard plus pynput's Ctrl+V. Wayland uses wl-clipboard plus a virtual keyboard,
because a tray-only app has no focus there and so can't set the Qt clipboard or fake keys."""
import subprocess
import time

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

from .session import IS_WAYLAND

RESTORE_MS = 250
WAYLAND_RESTORE_MS = 400  # Electron apps read the clipboard a bit later
SETTLE_MS = 50  # lets the clipboard owner change before Ctrl+V
DEVICE_WARMUP = 0.6  # seconds a new virtual keyboard needs before the compositor listens to it
_keys = None
_virtual = None


def _snapshot(src: QMimeData) -> QMimeData:
    copy = QMimeData()
    for fmt in src.formats():
        copy.setData(fmt, src.data(fmt))
    if src.hasImage():
        copy.setImageData(src.imageData())
    return copy


def _paste_qt(text: str) -> bool:
    global _keys
    from pynput.keyboard import Controller, Key

    _keys = _keys or Controller()
    clipboard = QGuiApplication.clipboard()
    saved = _snapshot(clipboard.mimeData())
    clipboard.setText(text)
    with _keys.pressed(Key.ctrl):
        _keys.tap("v")
    QTimer.singleShot(RESTORE_MS, lambda: clipboard.setMimeData(saved))
    return True


def _wl_paste_text() -> str | None:
    """The current clipboard as text, or None when it is empty or not text."""
    try:
        out = subprocess.run(["wl-paste", "-n", "--type", "text"], capture_output=True, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def _wl_copy(text: str | None) -> None:
    """Puts text on the clipboard (or clears it for None) without needing keyboard focus."""
    args, data = (["wl-copy"], text.encode()) if text is not None else (["wl-copy", "--clear"], None)
    try:  # DEVNULL, not pipes: wl-copy leaves a background process that would keep a pipe open
        subprocess.run(args, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    except (OSError, subprocess.SubprocessError):
        pass


def prepare() -> None:
    """Creates the Wayland virtual keyboard early (call once at startup; harmless elsewhere)."""
    global _virtual
    if IS_WAYLAND and _virtual is None:
        from .evdev_input import VirtualKeyboard, can_type

        if can_type():
            try:
                _virtual = VirtualKeyboard()
            except Exception:
                _virtual = None


def _paste_wayland(text: str) -> bool:
    previous = _wl_paste_text()
    _wl_copy(text)
    if _virtual is None:
        return False  # the text is on the clipboard; the user presses Ctrl+V
    wait = max(0.0, DEVICE_WARMUP - (time.monotonic() - _virtual.created_at))
    time.sleep(wait + SETTLE_MS / 1000)
    _virtual.ctrl_v()
    QTimer.singleShot(WAYLAND_RESTORE_MS, lambda: _wl_copy(previous))
    return True


def paste(text: str) -> bool:
    """Types the text into the focused window. Returns False when it could only be copied (press Ctrl+V)."""
    return _paste_wayland(text) if IS_WAYLAND else _paste_qt(text)
