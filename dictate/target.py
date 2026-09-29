"""Where the glow goes: the focused textbox, else the foreground window. All rectangles are
(left, top, right, bottom) in physical screen pixels."""
import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger("dictate")

UIA_EDIT, UIA_DOCUMENT = 50004, 50030
MIN_SIZE = 12  # Smaller controls (checkboxes, icons) are not textboxes.
DWMWA_EXTENDED_FRAME_BOUNDS = 9  # The visible window, without its invisible resize border.

_user32 = ctypes.windll.user32
_user32.GetForegroundWindow.restype = wintypes.HWND
_uia = None  # UI Automation must be used from the thread that created it.


def init_uia() -> None:
    """Sets up UI Automation on the calling thread, which must also be the one that calls textbox_rect()."""
    global _uia
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        _uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    except Exception:
        log.exception("UI Automation unavailable; the glow will surround the window instead")


def textbox_rect() -> tuple[int, int, int, int] | None:
    """The focused text field, or None when the focus is elsewhere (or the app doesn't expose it)."""
    try:
        element = _uia.GetFocusedElement()
        if element.CurrentControlType not in (UIA_EDIT, UIA_DOCUMENT):
            return None
        r = element.CurrentBoundingRectangle
    except Exception:  # No focus, the app went away, or UI Automation isn't available.
        return None
    if r.right - r.left < MIN_SIZE or r.bottom - r.top < MIN_SIZE:
        return None
    return r.left, r.top, r.right, r.bottom


def foreground_rect() -> tuple[int, int, int, int]:
    """The active window, or the whole screen when there isn't one."""
    hwnd = _user32.GetForegroundWindow()
    rect = wintypes.RECT()
    if hwnd and (
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) == 0
        or _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)
