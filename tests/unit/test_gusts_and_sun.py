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


def test_the_launch_gust_is_at_least_the_model_gust_and_the_launch_wind(rules):
    assert estimate_gusts(30, 20, 20, rules)[0] == 30  # the model's gust is larger
    assert estimate_gusts(0, 20, 20, rules)[0] == 20  # no extra wind aloft: the launch wind


def test_faster_air_at_the_top_of_the_thermals_raises_the_launch_gust(rules):
    launch, aloft = estimate_gusts(10, 20, 60, rules)
    assert launch == pytest.approx(20 + rules.gust_mix_fraction * 40)
    assert aloft == pytest.approx(60 * rules.gust_aloft_factor)


def test_slower_air_aloft_never_lowers_the_launch_gust(rules):
    assert estimate_gusts(10, 20, 5, rules)[0] == 20


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
    assert b.verdict_pg in ("turbulent", "dangerous")
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
    assert b.verdict_pg == "dangerous" and any("thermal height" in r for r in b.reasons)


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
