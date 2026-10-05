import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from ffforecast.config import ConfigError, load_rules
from ffforecast.diagnostics import build_block, estimate_gusts, sun_from_cloud
from ffforecast.grading import grade_weather
from ffforecast.models import Wind
from ffforecast.thermal import Thermal

START = datetime(2026, 10, 6, 13, tzinfo=timezone(timedelta(hours=11)))


def block(rules, *, thermal=None, ground=10, aloft=14, launch=12, gust=0, sun=None):
    return build_block(
        START, Wind(350, ground), Wind(10, aloft), 1500, 380, 16, 785, rules,
        gust_kph=gust, launch=Wind(350, launch), thermal=thermal, sun_pct_gfs=sun,
    )  # fmt: skip


# ---- estimating gusts


def test_the_launch_gust_is_at_least_the_model_gust_and_a_multiple_of_the_launch_wind(rules):
    assert estimate_gusts(40, 20, 20, rules)[0] == 40  # the model's gust is larger
    # no extra wind aloft and no model gust: the floor, a multiple of the launch wind
    assert estimate_gusts(0, 20, 20, rules)[0] == pytest.approx(20 * rules.gust_factor_floor)


def test_faster_air_at_the_top_of_the_thermals_raises_the_launch_gust(rules):
    launch, aloft = estimate_gusts(10, 20, 60, rules)
    assert launch == pytest.approx(20 + rules.gust_mix_fraction * 40)
    assert aloft == pytest.approx(60 * rules.gust_aloft_factor)


def test_slower_air_aloft_never_lowers_the_launch_gust(rules):
    assert estimate_gusts(10, 20, 5, rules)[0] == pytest.approx(20 * rules.gust_factor_floor)


def test_monday_noon_gusts_reach_what_the_station_measured(rules):
    """2026-10-05 12:00: AUSRASP 18 kph at 10 m and 32 kph at the top of the thermals; the station
    measured gusts of 29 to 31 kph. The estimate had been 25 kph, a kph under the Turbulent limit."""
    launch_gust, _ = estimate_gusts(15, 18, 32, rules)
    assert launch_gust >= 27
    assert grade_weather(0, 0, launch_gust, rules)[0][0] == "turbulent"


# ---- grading on gusts aloft


def test_gusts_aloft_make_turbulent_then_dangerous(rules):
    orange = 28 * 1.609344 + 1
    red = 34 * 1.609344 + 1
    assert grade_weather(0, 0, 0, rules, gust_aloft_kph=20) == []
    assert grade_weather(0, 0, 0, rules, gust_aloft_kph=orange)[0][0] == "turbulent"
    state, reason = grade_weather(0, 0, 0, rules, gust_aloft_kph=red)[0]
    assert state == "dangerous" and "thermal height" in reason


# ---- sunshine


def test_gfs_cloud_cover_gives_the_sun_that_gets_through(rules):
    assert sun_from_cloud(0, 0, 0, rules) == 100
    assert sun_from_cloud(100, 0, 0, rules) == pytest.approx(10)  # overcast low cloud
    assert sun_from_cloud(0, 0, 100, rules) == pytest.approx(75)  # high cloud stops little


def test_shading_lowers_the_thermal_quality_and_is_explained(rules):
    sunny = block(rules, sun=90)
    shaded = block(rules, sun=35)
    assert shaded.thermal_quality_pct < sunny.thermal_quality_pct
    assert any("Cloud shading" in r for r in shaded.reasons) and shaded.sun_pct == 35
    assert shaded.sun_source == "gfs"
    assert not any("shading" in r for r in sunny.reasons)


def test_ausrasp_sun_is_preferred_to_the_gfs_estimate(rules):
    t = Thermal(1800, 2, "2026-10-05T12:00:00Z", 3.0, 8.0, 55.0)
    b = block(rules, thermal=t, sun=95)
    assert (b.sun_pct, b.sun_source) == (55, "ausrasp")


def test_no_sun_figure_leaves_the_block_alone(rules):
    b = block(rules)
    assert b.sun_pct is None and b.sun_source == ""


# ---- AUSRASP's wind


def test_a_stronger_ausrasp_wind_is_graded_on_and_says_so(rules):
    t = Thermal(1800, 2, "r", sfc_wind_ms=8.0, top_wind_ms=10.0, sun_pct=90.0)  # 29 kph at 10 m
    b = block(rules, thermal=t, launch=8)
    assert b.verdict_pg == "bad"
    assert any("AUSRASP's regional model" in r for r in b.reasons)
    assert b.wind_ausrasp_kph == 29 and b.wind_top_kph == 36


def test_the_ausrasp_wind_can_be_switched_off(rules):
    t = Thermal(1800, 2, "r", sfc_wind_ms=8.0, top_wind_ms=3.0, sun_pct=90.0)
    off = dataclasses.replace(rules, ausrasp_wind_counts=False)
    b = block(off, thermal=t, launch=8)
    assert not any("AUSRASP's regional model" in r for r in b.reasons)


def test_a_weaker_ausrasp_wind_changes_nothing(rules):
    t = Thermal(1800, 2, "r", sfc_wind_ms=1.0, top_wind_ms=3.0, sun_pct=90.0)
    assert not any("AUSRASP's regional model" in r for r in block(rules, thermal=t).reasons)


def test_a_block_with_a_big_wind_aloft_is_called_rough_even_with_a_light_surface(rules):
    t = Thermal(1800, 2, "r", sfc_wind_ms=2.0, top_wind_ms=16.0, sun_pct=90.0)  # 58 kph aloft
    b = block(rules, thermal=t, ground=5, aloft=14, launch=6)
    assert b.gust_aloft_kph == round(16 * 3.6 * rules.gust_aloft_factor)
    assert b.verdict_pg == "bad" and any("thermal height" in r for r in b.reasons)


# ---- the rules file


def test_the_rules_load_with_the_new_values(rules):
    assert rules.gust_mix_fraction == 0.5 and rules.sun_full_pct == 70
    assert rules.gust_aloft_orange_from_mph < rules.gust_aloft_red_from_mph
    assert rules.ausrasp_wind_counts is True


def write(tmp_path, text):
    p = tmp_path / "rules.toml"
    p.write_text(text)
    return p


def test_bad_gust_and_sun_values_are_refused(tmp_path):
    from pathlib import Path

    ok = Path(__file__).resolve().parents[2].joinpath("config/rules.toml").read_text()
    for bad, match in (
        ("gust_mix_fraction = 0.5", "gust_mix_fraction"),
        ("gust_aloft_factor = 1.25", "gust_aloft_factor"),
        ("full_pct = 70", "full_pct"),
    ):
        value = {"gust_mix_fraction": "2", "gust_aloft_factor": "0.5", "full_pct": "20"}[
            bad.split(" =")[0]
        ]
        text = ok.replace(bad, f"{bad.split(' =')[0]} = {value}")
        with pytest.raises(ConfigError, match=match):
            load_rules(write(tmp_path, text))


# ---- hang gliders cope with more gust, as they do with more wind


def test_hang_glider_gust_limits_are_scaled_by_their_wind_bands(rules):
    from ffforecast.grading import gust_limits_mph

    pg = gust_limits_mph(rules, "pg")
    hg = gust_limits_mph(rules, "hg")
    assert pg[:2] == (rules.gust_orange_from_mph, rules.gust_red_from_mph)
    assert hg[0] == pytest.approx(rules.gust_orange_from_mph * 14 / 12)
    assert hg[1] == pytest.approx(rules.gust_red_from_mph * 20 / 14)
    assert all(h > p for h, p in zip(hg, pg, strict=True))


def test_a_gust_that_is_bad_for_a_paraglider_can_be_fine_for_a_hang_glider(rules):
    gust_kph = 28.0  # 17.4 mph: over the paraglider limit (16), under the hang glider's (18.7)
    assert grade_weather(0, 0, gust_kph, rules, glider="pg")[0][0] == "turbulent"
    assert grade_weather(0, 0, gust_kph, rules, glider="hg") == []


def test_the_floor_does_not_make_a_hang_glider_wind_band_meaningless(rules):
    """The gust floor (1.5 x the wind) passes the paraglider gust limit below the paraglider wind
    limit; scaling the hang glider's limits keeps its higher wind tolerance."""
    wind = (
        19.5  # kph: just over the paraglider wind limit (12 mph), well under the hang glider's (14)
    )
    b = build_block(
        START, Wind(350, wind), Wind(10, wind), 1500, 380, 16, 785, rules, launch=Wind(350, wind)
    )
    assert b.verdict_pg == "bad" and b.verdict_hg != "bad"
