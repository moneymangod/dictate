"""Wayland backend: reads the keyboard straight from /dev/input (python-evdev) and types through a virtual
keyboard (/dev/uinput). Wayland gives normal apps no global key hook and no fake keystrokes, so this is the
way that works on every compositor, KDE Plasma included. It needs the user to be in the `input` group
(install-linux.sh sets that up). The keyboard is only read, never grabbed, so Shift keeps working normally."""
import glob
import logging
import os
import select
import shutil
import threading
import time
from typing import Callable

log = logging.getLogger("dictate")

VIRTUAL_NAME = "Dictate virtual keyboard"
RESCAN_SECONDS = 3.0  # picks up keyboards that are plugged in later


def can_read_keyboards() -> bool:
    return any(os.access(path, os.R_OK) for path in glob.glob("/dev/input/event*"))


def can_type() -> bool:
    return os.access("/dev/uinput", os.W_OK)


def setup_problem() -> str:
    """What is missing for Dictate to work on Wayland, in plain words ("" when all is fine)."""
    try:
        import evdev  # noqa: F401
    except ImportError:
        return "The Python package evdev is missing. Run install-linux.sh."
    if not can_read_keyboards():
        return "Dictate can't read the keyboard yet. Run install-linux.sh once, then log out and back in."
    if shutil.which("wl-copy") is None:
        return "wl-clipboard is missing. Install it: sudo dnf install wl-clipboard"
    if not can_type():
        return "Dictate can't type for you yet, so it will only copy the text: press Ctrl+V. Run install-linux.sh once, then log out and back in."
    return ""


def is_keyboard(keys: list[int], name: str) -> bool:
    """A real keyboard (has letters and Right Shift), not our own virtual one."""
    from evdev import ecodes

    return name != VIRTUAL_NAME and ecodes.KEY_A in keys and ecodes.KEY_RIGHTSHIFT in keys


class KeyWatcher(threading.Thread):
    """Calls on_press / on_release when Right Shift goes down / up on any keyboard."""

    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]):
        super().__init__(name="evdev-keys", daemon=True)
        self._on_press, self._on_release = on_press, on_release
        self._stop_flag = threading.Event()

    def stop(self) -> None:
        self._stop_flag.set()

    def _scan(self, devices: dict) -> None:
        from evdev import InputDevice, ecodes, list_devices

        for path in list_devices():
            if path in devices:
                continue
            try:
                dev = InputDevice(path)
                if is_keyboard(dev.capabilities().get(ecodes.EV_KEY, []), dev.name):
                    devices[path] = dev
                else:
                    dev.close()
            except OSError:  # no permission, or unplugged meanwhile
                pass

    def run(self) -> None:
        from evdev import ecodes

        devices: dict = {}
        next_scan = 0.0
        while not self._stop_flag.is_set():
            if time.monotonic() >= next_scan:
                self._scan(devices)
                next_scan = time.monotonic() + RESCAN_SECONDS
            if not devices:
                self._stop_flag.wait(1.0)
                continue
            ready, _, _ = select.select(list(devices.values()), [], [], 0.5)
            for dev in ready:
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY and event.code == ecodes.KEY_RIGHTSHIFT:
                            if event.value == 1:
                                self._on_press()
                            elif event.value == 0:
                                self._on_release()
                except OSError:  # keyboard unplugged
                    devices = {p: d for p, d in devices.items() if d is not dev}
                    dev.close()
        for dev in devices.values():
            dev.close()


class VirtualKeyboard:
    """Sends Ctrl+V. Created once at startup: the compositor needs a moment to notice a new device,
    and keys sent before that are silently lost."""

    def __init__(self):
        from evdev import UInput, ecodes

        self._ecodes = ecodes
        self._ui = UInput({ecodes.EV_KEY: [ecodes.KEY_LEFTCTRL, ecodes.KEY_V]}, name=VIRTUAL_NAME)
        self.created_at = time.monotonic()

    def ctrl_v(self) -> None:
        e = self._ecodes
        for code, value in ((e.KEY_LEFTCTRL, 1), (e.KEY_V, 1), (e.KEY_V, 0), (e.KEY_LEFTCTRL, 0)):
            self._ui.write(e.EV_KEY, code, value)
            self._ui.syn()

    def close(self) -> None:
        self._ui.close()
