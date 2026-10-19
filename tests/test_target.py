from dictate import target


def test_foreground_rect_is_a_real_rectangle():
    left, top, right, bottom = target.foreground_rect()
    assert right > left and bottom > top


def test_foreground_rect_falls_back_without_windows_apis(monkeypatch):
    monkeypatch.setattr(target, "_user32", None)
    assert target.foreground_rect() == (0, 0, 1, 1)
