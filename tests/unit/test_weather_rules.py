import dataclasses

import pytest

from ffforecast.config import ConfigError, load_rules
from ffforecast.grading import grade_block, grade_weather
from ffforecast.units import mph_to_kph


def states(rules, **kw):
    return [
        s for s, _ in grade_weather(kw.get("rain", 0), kw.get("cape", 0), kw.get("gust", 0), rules)
    ]


def test_dry_calm_day_has_no_weather_problems(rules):
    assert grade_weather(0, 200, 10, rules) == []


def test_light_rain_is_poor_heavy_rain_is_dangerous(rules):
    assert states(rules, rain=0.3) == ["poor"]
    assert states(rules, rain=1.5) == ["dangerous"]


def test_storm_energy_levels(rules):
    assert states(rules, cape=300) == []
    assert states(rules, cape=600) == ["turbulent"]  # overdevelopment risk, no rain
    assert states(rules, cape=1200) == ["dangerous"]
    # rain with moderate energy escalates to a storm risk
    assert sorted(states(rules, rain=0.3, cape=600)) == ["dangerous", "poor"]


def test_gust_bands(rules):
    assert states(rules, gust=mph_to_kph(15)) == []
    assert states(rules, gust=mph_to_kph(17)) == ["turbulent"]
    assert states(rules, gust=mph_to_kph(21)) == ["dangerous"]


def test_todays_real_case_is_not_good(rules):
    # GFS at the launch at 11:00 on 3 Oct 2026: 2.3 mm/h, CAPE 648, light wind in the sector.
    v, reasons = grade_block(350, 5, 8, 60, 1500, rules, rain_mm_h=2.3, cape_j_kg=648, gust_kph=7)
    assert v == "dangerous"
    assert any("Heavy rain" in r for r in reasons) and any("Thunderstorm" in r for r in reasons)


def test_rain_beats_ok_thermals(rules):
    v, _ = grade_block(0, 10, 10, 90, 2000, rules, rain_mm_h=0.2)
    assert v == "poor"


def test_hang_gliders_also_stop_for_storms(rules):
    v, _ = grade_block(0, 10, 10, 90, 2000, rules, "hg", cape_j_kg=1500)
    assert v == "dangerous"


def test_thresholds_are_tunable(rules):
    lax = dataclasses.replace(rules, rain_light_mm_h=1.0)
    assert grade_weather(0.5, 0, 0, lax) == []


def test_weather_config_validated(tmp_path, rules):
    text = open("config/rules.toml").read()
    bad = text.replace("rain_light_mm_h = 0.1", "rain_light_mm_h = 5")
    p = tmp_path / "r.toml"
    p.write_text(bad)
    with pytest.raises(ConfigError, match="rain_light"):
        load_rules(p)


def test_old_rules_without_weather_section_still_load(tmp_path):
    text = open("config/rules.toml").read().split("[weather]")[0]
    p = tmp_path / "r.toml"
    p.write_text(text)
    r = load_rules(p)
    assert r.rain_light_mm_h == 0.1 and r.cape_storm_j_kg == 1000
