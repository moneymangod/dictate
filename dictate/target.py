"""Which window is active, so the glow goes on the screen you are working on."""
import ctypes
from ctypes import wintypes

DWMWA_EXTENDED_FRAME_BOUNDS = 9  # The visible window, without its invisible resize border.

_windll = getattr(ctypes, "windll", None)
_user32 = getattr(_windll, "user32", None)
_dwmapi = getattr(_windll, "dwmapi", None)
if _user32 is not None:
    _user32.GetForegroundWindow.restype = wintypes.HWND


def foreground_rect() -> tuple[int, int, int, int]:
    """The active window as (left, top, right, bottom) physical pixels, or the whole screen when there isn't one."""
    if _user32 is None:
        return 0, 0, 1, 1
    hwnd = _user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if hwnd and (
        (_dwmapi is not None and _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) == 0)
        or _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ):
        return rect.left, rect.top, rect.right, rect.bottom
    width, height = _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
    return 0, 0, width or 1, height or 1


def kwin_active_output() -> str:
    """The name of the output KDE's window manager says is active (e.g. "DP-1"), or "" when unknown."""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return ""
        reply = QDBusInterface("org.kde.KWin", "/KWin", "org.kde.KWin", bus).call("activeOutputName")
        if reply.type() == QDBusMessage.ReplyMessage and reply.arguments():
            return str(reply.arguments()[0])
    except Exception:
        pass
    return ""


def linux_active_screen():
    """The screen you are working on: KDE's active output, else the one under the mouse, else the primary."""
    from PySide6.QtGui import QCursor, QGuiApplication

    name = kwin_active_output()
    screen = next((s for s in QGuiApplication.screens() if name and s.name() == name), None)
    return screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
