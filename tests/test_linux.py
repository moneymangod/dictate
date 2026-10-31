import os

import pytest

from dictate import session


def test_data_dir_follows_xdg_on_linux(monkeypatch):
    monkeypatch.setattr(session, "IS_WINDOWS", False)
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg")
    assert session.data_dir() == os.path.join("/tmp/xdg", "Dictate")
    monkeypatch.delenv("XDG_DATA_HOME")
    assert session.data_dir().endswith(os.path.join(".local", "share", "Dictate"))


def test_mic_hint_is_not_windows_text_on_linux(monkeypatch):
    monkeypatch.setattr(session, "IS_WINDOWS", False)
    assert "Windows" not in session.mic_settings_hint()


def test_right_shift_ignores_auto_repeat():
    from dictate.hotkey import RightShift

    shift, events = RightShift(), []
    shift.pressed.connect(lambda: events.append("down"))
    shift.released.connect(lambda: events.append("up"))
    for step in (shift._on_press, shift._on_press, shift._on_release, shift._on_release):
        step()
    assert events == ["down", "up"]


def test_only_real_keyboards_are_watched():
    evdev = pytest.importorskip("evdev", reason="evdev is Linux only")
    from dictate.evdev_input import VIRTUAL_NAME, is_keyboard

    keys = [evdev.ecodes.KEY_A, evdev.ecodes.KEY_RIGHTSHIFT]
    assert is_keyboard(keys, "AT Translated Set 2 keyboard")
    assert not is_keyboard(keys, VIRTUAL_NAME)  # our own virtual keyboard
    assert not is_keyboard([evdev.ecodes.BTN_LEFT], "Mouse")


def test_wayland_paste_without_uinput_only_copies(monkeypatch):
    pytest.importorskip("PySide6.QtGui", reason="Qt runtime not available", exc_type=ImportError)
    from dictate import inserter

    copied = []
    monkeypatch.setattr(inserter, "IS_WAYLAND", True)
    monkeypatch.setattr(inserter, "_virtual", None)
    monkeypatch.setattr(inserter, "_wl_paste_text", lambda: "old")
    monkeypatch.setattr(inserter, "_wl_copy", copied.append)
    assert inserter.paste("hello ") is False  # the user has to press Ctrl+V
    assert copied == ["hello "]
