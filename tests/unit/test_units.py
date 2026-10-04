import pytest

from ffforecast.units import angle_diff, deg_to_compass, kph_to_mph, mph_to_kph, wind_from_uv


def test_mph_kph_round_trip():
    assert mph_to_kph(12) == pytest.approx(19.31, abs=0.01)
    assert mph_to_kph(14) == pytest.approx(22.53, abs=0.01)
    assert kph_to_mph(mph_to_kph(7)) == pytest.approx(7)


@pytest.mark.parametrize(
    "deg,name", [(0, "N"), (359, "N"), (90, "E"), (200, "SSW"), (67, "ENE"), (350, "N"), (11, "N")]
)
def test_compass(deg, name):
    assert deg_to_compass(deg) == name


@pytest.mark.parametrize("a,b,d", [(10, 350, 20), (0, 180, 180), (90, 90, 0), (350, 10, 20)])
def test_angle_diff(a, b, d):
    assert angle_diff(a, b) == d


def test_wind_from_uv_directions():
    # wind blowing toward the east (u>0) comes FROM the west
    d, s = wind_from_uv(5, 0)
    assert d == pytest.approx(270) and s == pytest.approx(5)
    d, _ = wind_from_uv(0, -5)  # blowing toward the south: from the north
    assert d == pytest.approx(0) or d == pytest.approx(360)
