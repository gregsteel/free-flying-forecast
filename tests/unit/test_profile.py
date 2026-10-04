import math

import pytest

from ffforecast.profile import usable_profile, wind_at


def test_interpolates_between_two_levels():
    pts = [(700.0, 0.0, -4.0), (900.0, 0.0, -8.0)]  # northerly, 4 then 8 m/s
    d, s = wind_at(800.0, pts)
    assert s == pytest.approx(6.0) and (d < 1 or d > 359)


def test_direction_turns_with_height():
    pts = [(700.0, 0.0, -5.0), (900.0, 5.0, 0.0)]  # north wind below, west wind above
    d, s = wind_at(800.0, pts)
    assert 310 < d < 320  # NW halfway between N (360) and W (270)
    assert s == pytest.approx(math.hypot(2.5, 2.5))


def test_outside_the_profile_uses_nearest_end():
    pts = [(700.0, 0.0, -4.0), (900.0, 0.0, -8.0)]
    assert wind_at(100.0, pts)[1] == pytest.approx(4.0)
    assert wind_at(3000.0, pts)[1] == pytest.approx(8.0)


def test_empty_profile_is_an_error():
    with pytest.raises(ValueError):
        wind_at(800.0, [])


def test_levels_below_model_ground_are_dropped():
    # surface pressure 940 hPa: 950 hPa is underground (extrapolated), 925 and 900 are valid
    levels = {950: (540.0, 9.0, 9.0), 925: (800.0, 1.0, -3.0), 900: (1030.0, 2.0, -6.0)}
    pts = usable_profile(687.0, 94000.0, 0.5, -1.0, levels)
    assert [round(p[0]) for p in pts] == [697, 800, 1030]  # no 540 m point
    assert (9, 9) not in [(p[1], p[2]) for p in pts]


def test_levels_must_rise_above_the_surface_point():
    pts = usable_profile(687.0, 94000.0, 0.0, -1.0, {925: (690.0, 1.0, 1.0)})
    assert len(pts) == 1  # 690 m is below the 697 m surface point, so it is ignored


def test_launch_wind_from_a_real_style_profile():
    # numbers from the 11:00 3 Oct file: orog 687 m, 940 hPa; ~800 m sits just above the surface
    levels = {925: (803.0, -0.9, -3.4), 900: (1032.0, 0.1, -3.0)}
    d, s = wind_at(800.0, usable_profile(687.0, 94014.0, -0.43, -0.92, levels))
    assert 0 < s < 6
