import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dictate import voicebar
from dictate.voicebar import BARS, HIGH, LOW, VoiceBar


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def run(bar: VoiceBar, seconds: float) -> None:
    start = t = bar._last
    while t < start + seconds:
        t += 1 / 60
        bar.advance(t)


def test_bars_follow_the_voice_and_the_middle_moves_most(qapp):
    loud, quiet = VoiceBar(lambda: 1.0), VoiceBar(lambda: 0.0)
    for bar in (loud, quiet):
        bar.listen()
        run(bar, 1.0)
    assert max(loud._heights) > HIGH * 0.6 and max(quiet._heights) < LOW + 4
    assert max(loud._heights) > loud._heights[0] and max(loud._heights) > loud._heights[BARS - 1]


def test_pill_sits_at_the_bottom_centre_above_the_taskbar(qapp):
    bar = VoiceBar(lambda: 0.0)
    bar.listen()
    run(bar, 0.5)
    area = qapp.primaryScreen().availableGeometry()
    assert abs(bar.geometry().center().x() - area.center().x()) <= 1
    assert bar.geometry().bottom() < area.bottom() and bar.geometry().top() > area.height() * 0.8


def test_transcribing_rolls_a_wave_and_dismiss_hides(qapp):
    bar = VoiceBar(lambda: 1.0)
    bar.listen()
    run(bar, 0.5)
    bar.transcribing()
    run(bar, 0.5)
    assert max(bar._heights) - min(bar._heights) > 3  # bars differ: a wave, not a flat line
    bar.dismiss()
    run(bar, 0.6)
    assert bar._state == "hidden" and not bar.isVisible() and not bar._timer.isActive()


def test_pressing_again_while_leaving_brings_it_back(qapp):
    bar = VoiceBar(lambda: 0.5)
    bar.listen()
    run(bar, 0.4)
    bar.dismiss()
    run(bar, 0.1)
    bar.listen()
    run(bar, 0.4)
    assert bar._state == "listening" and bar._alpha > 0.9
