import pytest

from ffforecast.diagnostics import (
    shear_class,
    thermal_height_asl,
    thermal_quality_pct,
    wstar,
)
from ffforecast.models import Wind


def test_wstar_typical_value():
    # 250 W/m2 into a 1500 m boundary layer: about 2.2-2.4 m/s
    assert wstar(250, 1500, 289) == pytest.approx(2.3, abs=0.2)


def test_wstar_zero_without_heating():
    assert wstar(0, 1500, 289) == 0
    assert wstar(-20, 1500, 289) == 0
    assert wstar(200, 0, 289) == 0


def test_wstar_grows_with_flux_and_depth():
    assert wstar(300, 1500, 289) > wstar(100, 1500, 289)
    assert wstar(200, 2000, 289) > wstar(200, 800, 289)


def test_thermal_height_is_above_sea_level():
    assert thermal_height_asl(1000, 785) == 1785


def test_quality_scale_and_wind_penalty():
    assert thermal_quality_pct(2.5, 10) == 100
    assert thermal_quality_pct(0, 10) == 0
    assert thermal_quality_pct(2.5, 25) < thermal_quality_pct(2.5, 10)
    assert thermal_quality_pct(1.0, 10) % 10 == 0


def test_shear(rules):
    assert shear_class(Wind(0, 10), Wind(0, 12), rules) == "light"
    assert shear_class(Wind(0, 10), Wind(0, 20), rules) == "moderate"
    assert shear_class(Wind(0, 10), Wind(180, 15), rules) == "strong"


# ---- usable thermal height and calibrated quality (see research.md section 21) ----------------


def test_thermals_below_the_critical_updraft_are_not_usable(rules):
    from ffforecast.diagnostics import usable_thermal_height_asl

    # 225 ft/min is 1.143 m/s: under it the height is the ground, however deep the boundary layer
    assert usable_thermal_height_asl(1800, 1.1, 800, rules) == 800
    assert usable_thermal_height_asl(1800, 0.0, 800, rules) == 800


def test_usable_height_is_about_half_the_boundary_layer_above_launch(rules):
    from ffforecast.diagnostics import usable_thermal_height_asl

    assert usable_thermal_height_asl(1800, 2.4, 800, rules) == pytest.approx(800 + 0.48 * 1800)
    # well under the top of the boundary layer, which is what the old figure reported
    assert usable_thermal_height_asl(1800, 2.4, 800, rules) < 800 + 1800


def test_a_no_thermal_hour_has_zero_depth_even_with_a_deep_layer(rules):
    from ffforecast.diagnostics import usable_thermal_height_asl

    assert usable_thermal_height_asl(0, 3.0, 800, rules) == 800  # no layer at all


def test_quality_is_full_at_the_calibrated_updraft_and_losing_to_wind():
    from ffforecast.diagnostics import thermal_quality_pct

    assert thermal_quality_pct(1.6, 10) == 100
    assert thermal_quality_pct(0.8, 10) == 50
    assert thermal_quality_pct(1.6, 12) == 100  # at the threshold: no penalty
    assert thermal_quality_pct(1.6, 20) == 80  # 8 kph over, 2.5 each
    assert thermal_quality_pct(2.5, 40) < thermal_quality_pct(2.5, 14)


def test_quality_matches_the_ausrasp_based_figures_better_than_the_old_formula():
    # (updraft m/s, wind kph, the reference quality %) from a table on 2026-10-03, wind as it shows it
    from ffforecast.diagnostics import thermal_quality_pct

    points = [
        (1.42, 14, 70), (1.94, 14, 100), (1.86, 11, 100), (2.33, 14, 100), (2.38, 18, 80),
        (1.97, 18, 80), (2.1, 18, 100), (2.16, 14, 100), (1.82, 14, 90), (2.0, 11, 100),
        (1.72, 14, 90), (2.25, 29, 50), (2.13, 36, 40), (1.73, 40, 30), (1.41, 32, 30),
        (2.06, 40, 30), (2.29, 36, 40), (0.52, 14, 20), (0.3, 29, 10),
    ]  # fmt: skip

    def old(w, wind):
        base = min(w / 2.5, 1.0) * 100
        return int(round(max(0.0, base - max(0.0, wind - 15) * 3) / 10) * 10)

    new_err = sum(abs(thermal_quality_pct(w, wd) - q) for w, wd, q in points) / len(points)
    old_err = sum(abs(old(w, wd) - q) for w, wd, q in points) / len(points)
    assert new_err < 10 and new_err < old_err / 2
