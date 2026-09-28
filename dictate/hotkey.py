"""Global Right Shift hook. The key is not suppressed, so Shift keeps working normally."""
from pynput import keyboard
from PySide6.QtCore import QObject, Signal


class RightShift(QObject):
    # Emitted from the hook thread; Qt queues them onto the main thread.
    pressed = Signal()
    released = Signal()

    def __init__(self):
        super().__init__()
        self._down = False
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()

    def _on_press(self, key) -> None:
        if key == keyboard.Key.shift_r and not self._down:  # Ignore auto-repeat.
            self._down = True
            self.pressed.emit()

    def _on_release(self, key) -> None:
        if key == keyboard.Key.shift_r and self._down:
            self._down = False
            self.released.emit()
