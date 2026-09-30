from dictate import target


def test_foreground_rect_is_a_real_rectangle():
    left, top, right, bottom = target.foreground_rect()
    assert right > left and bottom > top
