"""The collapsed 'How the numbers are calculated' section: every claim checked against the code."""

import dataclasses
import json
import math
import re
from datetime import UTC, datetime

import pytest

from ffforecast.diagnostics import (
    DRY_LAPSE_C_PER_M,
    build_block,
    thermal_quality_pct,
    usable_thermal_height_asl,
    wstar,
)
from ffforecast.models import Forecast, Wind
from ffforecast.render import render_page


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def method(html):
    a = html.index('<details class="guide" id="method">')
    return html[a : html.index("</details>", a)]


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_it_is_a_collapsed_section_after_the_guide(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert '<details class="guide" id="method">' in html  # no "open": collapsed
    assert (
        html.index('<details class="guide" id="guide">')
        < html.index('id="method"')
        < html.index("<footer>")
    )
    assert "<h2>How the numbers are calculated</h2>" in method(html)


def test_it_says_where_every_source_comes_from(fixture_path, site, rules):
    m = method(page(fixture_path, site, rules))
    t = text(m)
    assert "NOAA" in t and "GFS" in t and "25 km" in t
    assert "2026-10-03T00Z" in t  # the cycle, from the forecast itself
    assert "Nothing in the forecast is measured" in t  # model output, said plainly
    for name in ("Open-Meteo", "FreeFlightWx", "AUSRASP", "VHPA"):
        assert name in t
    for url in ("https://open-meteo.com/", "https://ausrasp.com/VIC/", "https://www.vhpa.org.au/"):
        assert f'href="{url}"' in m
    assert "the one measured source" in t  # the station chart, and only that


def test_it_names_the_model_used_for_this_run(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "NOAA GFS, WRF 4.6 (fixture)" in method(html)  # the data's own model label


def test_every_threshold_it_quotes_is_the_rules_value_in_every_unit(fixture_path, site, rules):
    m = method(page(fixture_path, site, rules))
    assert (
        '<span class="u a-m">1.1 m/s</span>' in m and '<span class="u a-ft">3.8 ft/sec</span>' in m
    )  # critical
    assert f"{rules.usable_depth_fraction * 100:.0f}%" in text(m)
    assert '<span class="u a-m">1.6 m/s</span>' in m  # 100% quality
    assert (
        '<span class="u s-kph">12 kph</span>' in m and '<span class="u s-kts">6 kts</span>' in m
    )  # wind threshold
    assert "2.5 points per km/h" in m and "4.6 points per knot" in m
    assert "9.8" in m  # the lapse rate


def test_it_follows_changed_rules(fixture_path, site, rules):
    tuned = dataclasses.replace(
        rules, usable_depth_fraction=0.6, quality_full_updraft_ms=2.0, critical_updraft_ms=1.0
    )
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    m = method(render_page(fc, site, tuned))
    assert "launch height ({" not in m and "60%" in text(m)
    assert '<span class="u a-m">2.0 m/s</span>' in m and '<span class="u a-m">1.0 m/s</span>' in m


# ---- the calculations it describes ------------------------------------------------------------


def test_updraft_is_the_convective_velocity_scale_it_describes():
    g, theta, cp, rho = 9.80665, 290.0, 1004.0, 1.1
    heating, depth = 250.0, 1500.0
    by_hand = ((g / theta) * (heating / (rho * cp)) * depth) ** (1 / 3)
    assert wstar(heating, depth, theta) == pytest.approx(by_hand)
    assert wstar(0, depth, theta) == 0 and wstar(-20, depth, theta) == 0  # "zero when not heating"
    assert wstar(300, depth, theta) > wstar(
        100, depth, theta
    )  # "stronger heating, stronger thermals"
    assert wstar(200, 2000, theta) > wstar(200, 800, theta)  # "a deeper layer, stronger thermals"


def test_thermal_height_is_what_the_text_says(rules):
    launch, depth = 800.0, 1800.0
    ok = usable_thermal_height_asl(depth, rules.critical_updraft_ms, launch, rules)
    assert ok == pytest.approx(launch + rules.usable_depth_fraction * depth)
    assert ok < launch + depth  # lower than the top of the boundary layer
    assert (
        usable_thermal_height_asl(depth, rules.critical_updraft_ms - 0.001, launch, rules) == launch
    )


def test_quality_is_what_the_text_says(rules):
    full, thr, pen = (
        rules.quality_full_updraft_ms,
        rules.quality_wind_threshold_kph,
        rules.quality_wind_penalty_per_kph,
    )
    args = (full, rules.quality_wind_threshold_kph, rules.quality_wind_penalty_per_kph)
    assert thermal_quality_pct(full, thr, *args) == 100  # 100% at the stated updraft
    assert thermal_quality_pct(full / 2, thr, *args) == 50  # in proportion below it
    over = 10.0
    assert (
        thermal_quality_pct(full, thr + over, *args) == round((100 - over * pen) / 10) * 10
    )  # minus the penalty
    assert thermal_quality_pct(0.83, 5, *args) % 10 == 0  # nearest 10


def test_temperature_at_thermal_height_is_taken_at_the_height_shown(rules):
    t0 = datetime(2026, 10, 4, 11, tzinfo=UTC)
    b = build_block(t0, Wind(0, 8), Wind(0, 8), 1800, 250, 16.0, 800, rules, launch=Wind(0, 8))
    climbed_km = (b.thermal_height_m - 800) / 1000
    assert b.temp_air_c == pytest.approx(
        16.0 - 9.8 * climbed_km, abs=0.1
    )  # the shown height, not the layer top
    assert DRY_LAPSE_C_PER_M == pytest.approx(0.0098)
    # and with no usable thermals there is no climb, so no cooling
    flat = build_block(t0, Wind(0, 8), Wind(0, 8), 1800, 0, 16.0, 800, rules, launch=Wind(0, 8))
    assert flat.thermal_height_m == 800 and flat.temp_air_c == 16.0


def test_the_wind_used_by_quality_is_the_stronger_of_ground_and_aloft(rules):
    t0 = datetime(2026, 10, 4, 11, tzinfo=UTC)
    calm = build_block(t0, Wind(0, 5), Wind(0, 5), 1800, 250, 16.0, 800, rules)
    windy_aloft = build_block(t0, Wind(0, 5), Wind(0, 40), 1800, 250, 16.0, 800, rules)
    assert (
        windy_aloft.thermal_quality_pct < calm.thermal_quality_pct
    )  # "the stronger of the 10 m and 850 hPa winds"


# ---- what is deliberately not on the page -------------------------------------------------------


def test_there_is_no_how_well_it_matches_section(fixture_path, site, rules):
    m = method(page(fixture_path, site, rules))
    assert "How well it matches" not in m
    assert "were compared with" not in m and "within about" not in m  # no comparison figures
    assert "<h3>Limitations</h3>" in m  # the limits stay: they are advice, not a scorecard


def test_the_page_does_not_name_the_muppet_forecast_anywhere(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "muppet" not in html.lower() and "lampdatabase" not in html.lower()
    assert "muppet" not in " ".join(site.links).lower()
    assert all("lampdatabase" not in v for v in site.links.values())


def test_ausrasp_is_always_written_in_capitals(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    visible = re.sub(r"<[^>]+>", " ", html)  # addresses (ausrasp.com) are lower case by nature
    assert "AUSRASP" in visible
    assert not re.search(r"AusRASP|Ausrasp|ausrasp(?!\.com)", visible)


def test_it_is_honest_about_the_limits(fixture_path, site, rules):
    t = text(method(page(fixture_path, site, rules)))
    assert "cannot see individual ridges" in t and "reasonable, not proven" in t
    assert math.isfinite(rules.usable_depth_fraction)
