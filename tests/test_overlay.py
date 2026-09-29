import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from dictate import overlay
from dictate.overlay import SCALE, TEXTBOX, WINDOW, EdgeGlow

WINDOW_RECT = (0, 0, 640, 480)  # stands in for the active window (the offscreen screen is 800x600)
TEXTBOX_RECT = (200, 200, 600, 260)


@pytest.fixture(autouse=True)
def fixed_window(monkeypatch):
    monkeypatch.setattr(overlay, "foreground_rect", lambda: WINDOW_RECT)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def run(glow: EdgeGlow, seconds: float) -> None:
    t = glow._since
    while t < glow._since + seconds:
        t += 1 / 60
        glow.advance(t)


def alpha(glow: EdgeGlow, side: str):
    return glow._buffers[side][..., 3]


def test_window_glow_is_valid_premultiplied_and_hugs_the_border(qapp):
    glow = EdgeGlow(lambda: 0.8)
    glow.listen()
    run(glow, 0.6)
    assert glow._look is WINDOW
    for side, buf in glow._buffers.items():
        assert (buf[..., :3] <= buf[..., 3:]).all(), f"{side}: color exceeds alpha (invalid premultiplied)"
    top, right = alpha(glow, "top"), alpha(glow, "right")
    assert top[0].mean() > 100 and top[0].mean() > 3 * top[-1].mean()  # bright on the border, fading inward
    assert right[:, -1].mean() > 100 and right[:, -1].mean() > 3 * right[:, 0].mean()


def test_textbox_glow_is_a_halo_that_leaves_the_text_alone(qapp):
    glow = EdgeGlow(lambda: 0.8)
    glow.listen(TEXTBOX_RECT)
    run(glow, 0.6)
    left, top, right, bottom = TEXTBOX_RECT
    assert glow._look is TEXTBOX
    assert glow._strips["top"].geometry() == QRect(left - TEXTBOX.out, top - TEXTBOX.out, right - left + 2 * TEXTBOX.out, TEXTBOX.out + TEXTBOX.inn)
    assert glow._strips["bottom"].geometry().bottom() + 1 == bottom + TEXTBOX.out

    top = alpha(glow, "top")
    middle = top[:, top.shape[1] // 2]  # down through the middle of the box's top border
    border = int(TEXTBOX.out * SCALE)  # the row on the border
    assert middle[border - 2 : border + 2].max() > 150  # bright rim on the border
    assert middle[0] < 5  # nothing far outside
    assert middle[border - 4] > 3 * middle[border + 4]  # 8 px out is much brighter than 8 px in, where the text is


def test_louder_voice_reaches_further_out(qapp):
    def reach(level: float) -> int:
        glow = EdgeGlow(lambda: level)
        glow.listen(TEXTBOX_RECT)
        run(glow, 0.8)
        top = alpha(glow, "top")
        return int((top[:, top.shape[1] // 2] > 20).sum())

    assert reach(1.0) > reach(0.0)


def test_glow_moves_onto_a_textbox_found_after_it_started(qapp):
    glow = EdgeGlow(lambda: 0.5)
    glow.listen()
    run(glow, 0.3)
    assert glow._look is WINDOW
    glow.retarget(TEXTBOX_RECT)
    run(glow, 0.5)
    assert glow._look is TEXTBOX and glow._alpha > 0.9  # crossfaded onto the box and faded back in
    assert glow._strips["top"].geometry().left() == TEXTBOX_RECT[0] - TEXTBOX.out


def test_late_textbox_is_ignored_once_transcribing(qapp):
    glow = EdgeGlow(lambda: 0.5)
    glow.listen()
    run(glow, 0.3)
    glow.transcribing()
    glow.retarget(TEXTBOX_RECT)
    run(glow, 0.5)
    assert glow._look is WINDOW


def test_tiny_rectangle_is_not_treated_as_a_textbox(qapp):
    glow = EdgeGlow(lambda: 0.5)
    glow.listen((10, 10, 15, 15))
    assert glow._look is WINDOW


def test_done_flashes_then_hides(qapp):
    glow = EdgeGlow(lambda: 0.5)
    glow.listen(TEXTBOX_RECT)
    run(glow, 0.3)
    glow.transcribing()
    run(glow, 0.3)
    glow.done()
    run(glow, 1.5)
    assert glow._state == "hidden" and not glow._timer.isActive()


def test_quick_press_fades_out_quietly(qapp):
    glow = EdgeGlow(lambda: 0.0)
    glow.listen(TEXTBOX_RECT)
    run(glow, 0.1)
    glow.discard()
    run(glow, 0.6)
    assert glow._state == "hidden"


def test_error_pulses_red_then_hides(qapp):
    glow = EdgeGlow(lambda: 0.0)
    glow.error()
    run(glow, 0.15)
    px = glow._buffers["top"][0]  # BGRA on the border
    assert px[..., 2].mean() > px[..., 0].mean() and px[..., 2].mean() > px[..., 1].mean()  # red dominates
    run(glow, 1.5)
    assert glow._state == "hidden"
