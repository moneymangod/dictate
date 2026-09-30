"""Which window is active, so the glow goes on the screen you are working on."""
import ctypes
from ctypes import wintypes

DWMWA_EXTENDED_FRAME_BOUNDS = 9  # The visible window, without its invisible resize border.

_user32 = ctypes.windll.user32
_user32.GetForegroundWindow.restype = wintypes.HWND


def foreground_rect() -> tuple[int, int, int, int]:
    """The active window as (left, top, right, bottom) physical pixels, or the whole screen when there isn't one."""
    hwnd = _user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if hwnd and (
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) == 0
        or _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
