"""Global Right Shift hook. The key is not suppressed, so Shift keeps working normally.
Windows and X11 use pynput; Wayland (Fedora KDE Plasma's default) reads the keyboard through evdev."""
from PySide6.QtCore import QObject, Signal

from .session import IS_WAYLAND


class RightShift(QObject):
    # Emitted from the hook thread; Qt queues them onto the main thread.
    pressed = Signal()
    released = Signal()

    def __init__(self):
        super().__init__()
        self._down = False
        self._listener = None

    def _make_listener(self):
        if IS_WAYLAND:
            from .evdev_input import KeyWatcher

            return KeyWatcher(self._on_press, self._on_release)
        from pynput import keyboard  # imported late: it needs a display to load on Linux

        self._shift_r = keyboard.Key.shift_r
        listener = keyboard.Listener(on_press=self._pynput_press, on_release=self._pynput_release)
        listener.daemon = True
        return listener

    def start(self) -> None:
        self._listener = self._make_listener()
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    def _pynput_press(self, key) -> None:
        if key == self._shift_r:
            self._on_press()

    def _pynput_release(self, key) -> None:
        if key == self._shift_r:
            self._on_release()

    def _on_press(self) -> None:
        if not self._down:  # Ignore auto-repeat.
            self._down = True
            self.pressed.emit()

    def _on_release(self) -> None:
        if self._down:
            self._down = False
            self.released.emit()
