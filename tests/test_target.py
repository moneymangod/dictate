from types import SimpleNamespace

import pytest

from dictate import target
from dictate.target import UIA_DOCUMENT, UIA_EDIT


def rect(left, top, right, bottom):
    return SimpleNamespace(left=left, top=top, right=right, bottom=bottom)


class FakeUia:
    def __init__(self, control_type, bounds):
        self.element = SimpleNamespace(CurrentControlType=control_type, CurrentBoundingRectangle=bounds)

    def GetFocusedElement(self):
        return self.element


@pytest.fixture
def uia(monkeypatch):
    def install(fake):
        monkeypatch.setattr(target, "_uia", fake)

    return install


def test_focused_text_field_is_found(uia):
    uia(FakeUia(UIA_EDIT, rect(100, 200, 500, 240)))
    assert target.textbox_rect() == (100, 200, 500, 240)
    uia(FakeUia(UIA_DOCUMENT, rect(0, 0, 900, 700)))
    assert target.textbox_rect() == (0, 0, 900, 700)


def test_other_focused_controls_are_not_textboxes(uia):
    uia(FakeUia(50000, rect(100, 200, 500, 240)))  # a button
    assert target.textbox_rect() is None
    uia(FakeUia(50032, rect(-9, -9, 1929, 1029)))  # a window
    assert target.textbox_rect() is None


def test_tiny_or_empty_fields_are_ignored(uia):
    uia(FakeUia(UIA_EDIT, rect(10, 10, 18, 40)))
    assert target.textbox_rect() is None
    uia(FakeUia(UIA_EDIT, rect(0, 0, 0, 0)))
    assert target.textbox_rect() is None


def test_lookup_failures_mean_no_textbox(uia):
    class Broken:
        def GetFocusedElement(self):
            raise OSError("the app went away")

    uia(Broken())
    assert target.textbox_rect() is None
    uia(None)  # UI Automation never initialised
    assert target.textbox_rect() is None


def test_foreground_rect_is_a_real_rectangle():
    left, top, right, bottom = target.foreground_rect()
    assert right > left and bottom > top
