import pytest

from options_risk_lab.american import reference
from options_risk_lab.pricing import bsm


def test_american_exercise_bounds_mesh_and_greek_bumps():
    exercise = reference(0.5, 1, 0.2, 0.05, 0, 256)
    assert exercise[0] == pytest.approx(50, abs=0.01)
    assert exercise[1] == pytest.approx(-1, abs=0.002)
    a = reference(1, 1, 0.2, 0.05, 0, 256)
    b = reference(1, 1, 0.2, 0.05, 0, 512)
    assert b[0] >= bsm(100, 100, 1, 0.2, kind="put").price
    assert abs(a[0] - b[0]) < 0.01
    assert abs(a[1] - b[1]) < 0.002
    assert abs(a[2] - b[2]) < 0.0005
    h = 0.002
    up = reference(1 + h, 1, 0.2, 0.05, 0, 512)[0]
    down = reference(1 - h, 1, 0.2, 0.05, 0, 512)[0]
    assert (up - down) / (0.4) == pytest.approx(b[1], abs=0.002)
