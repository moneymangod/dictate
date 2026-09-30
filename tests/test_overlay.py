import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dictate import overlay
from dictate.overlay import DEPTH, SCALE, EdgeGlow


@pytest.fixture(autouse=True)
def fixed_window(monkeypatch):
    monkeypatch.setattr(overlay, "foreground_rect", lambda: (0, 0, 640, 480))  # somewhere on the (offscreen) screen


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


def test_glow_frames_the_screen_and_hugs_its_border(qapp):
    glow = EdgeGlow(lambda: 0.8)
    glow.listen()
    run(glow, 1.0)
    screen = qapp.primaryScreen().geometry()
    assert glow._strips["top"].geometry().width() == screen.width() and glow._strips["left"].geometry().x() == 0
    assert glow._strips["bottom"].geometry().bottom() == screen.bottom()
    for side, buf in glow._buffers.items():
        assert (buf[..., :3] <= buf[..., 3:]).all(), f"{side}: color exceeds alpha (invalid premultiplied)"
    top, right = alpha(glow, "top"), alpha(glow, "right")
    assert top[0].mean() > 100 and top[0].mean() > 3 * top[-1].mean()  # bright on the border, fading inward
    assert right[:, -1].mean() > 100 and right[:, -1].mean() > 3 * right[:, 0].mean()


def test_louder_voice_reaches_further_in(qapp):
    def reach(level: float) -> int:
        glow = EdgeGlow(lambda: level)
        glow.listen()
        run(glow, 0.8)
        top = alpha(glow, "top")
        return int((top[:, top.shape[1] // 2] > 20).sum())

    assert reach(1.0) > reach(0.0)


def test_rim_draws_itself_on_from_the_top_edge(qapp):
    glow = EdgeGlow(lambda: 0.0)
    glow.listen()
    run(glow, 0.1)
    bottom = alpha(glow, "bottom")
    assert alpha(glow, "top")[0, alpha(glow, "top").shape[1] // 2] > 100  # the top's middle is lit first
    assert bottom[-1, bottom.shape[1] // 2] < 5  # the bottom's middle is not yet
    run(glow, 0.6)
    assert alpha(glow, "bottom")[-1, bottom.shape[1] // 2] > 100  # then all the way round


def test_done_sweeps_a_ring_inward_then_hides(qapp):
    glow = EdgeGlow(lambda: 0.5)
    glow.listen()
    run(glow, 0.6)
    glow.transcribing()
    run(glow, 0.3)
    glow.done()
    run(glow, 0.35)
    top = alpha(glow, "top")
    assert top[int(DEPTH * SCALE * 0.5) :, top.shape[1] // 2].max() > 25  # a ring well inside, where the bloom no longer reaches
    run(glow, 1.5)
    assert glow._state == "hidden" and not glow._timer.isActive()


def test_quick_press_fades_out_quietly(qapp):
    glow = EdgeGlow(lambda: 0.0)
    glow.listen()
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
