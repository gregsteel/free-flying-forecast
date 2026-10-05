import dataclasses
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from ffforecast.diagnostics import build_block
from ffforecast.grading import grade_block
from ffforecast.models import Forecast, Wind
from ffforecast.render import render_page
from ffforecast.units import mph_to_kph


def guide_html(fixture_path, site, rules):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    html = render_page(fc, site, rules)
    return html[html.index("<h2>Guide</h2>") : html.index('<details class="guide" id="method">')]


def text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_guide_names_every_factor_the_grading_uses(fixture_path, site, rules):
    g = text(guide_html(fixture_path, site, rules))
    for factor in ("Wind.", "Gusts.", "Rain and storms.", "Thermals.", "Hang gliders"):
        assert factor in g
    for word in ("direction", "rain", "storm energy", "CAPE", "thunderstorm", "gusts", "thermals"):
        assert word.lower() in g.lower()


def test_guide_is_honest_about_turbulence_and_shear(fixture_path, site, rules):
    g = text(guide_html(fixture_path, site, rules))
    assert "Turbulence is not measured" in g
    assert "does not change the grade" in g and "shear" in g.lower()


def test_guide_shows_the_real_thresholds_from_the_rules(fixture_path, site, rules):
    html = guide_html(fixture_path, site, rules)
    assert (
        f"{rules.cape_overdevelop_j_kg:.0f} J/kg" in html
        and f"{rules.cape_storm_j_kg:.0f} J/kg" in html
    )
    assert f"{mph_to_kph(rules.gust_orange_from_mph):.0f} kph" in html
    assert f"{mph_to_kph(rules.gust_red_from_mph):.0f} kph" in html
    assert f"{mph_to_kph(rules.speed_orange_from_mph):.0f} kph" in html
    assert (
        f"{rules.rain_light_mm_h:.1f} mm/h" in html and f"{rules.rain_heavy_mm_h:.1f} mm/h" in html
    )
    assert f"{rules.thermal_ok_quality_pct:.0f}%" in html
    assert f"no more than {rules.marginal_margin_deg:.0f} degrees outside it" in text(html)


def test_guide_follows_changed_rules(fixture_path, site, rules):
    tuned = dataclasses.replace(
        rules,
        cape_storm_j_kg=1500,
        gust_red_from_mph=30,
        rain_heavy_mm_h=3.0,
        thermal_ok_quality_pct=55,
    )
    g = guide_html(fixture_path, site, tuned)
    assert "1500 J/kg" in g and "3.0 mm/h" in g and "55%" in g
    assert f"{mph_to_kph(30):.0f} kph" in g


# Each claim in the Guide, checked against the real grading: (kwargs for grade_block, expected).
def claim_cases(r):
    base = dict(
        ground_dir=0, ground_kph=8, aloft_kph=8, thermal_quality_pct=70, thermal_height_m=1800
    )
    return [
        (
            "Ok: decent thermals, nothing wrong",
            dict(thermal_quality_pct=50, updraft_ms=1.2),
            "ok",
        ),
        (
            "Good: strong thermals, nothing wrong",
            dict(thermal_quality_pct=90, updraft_ms=2.7),
            "good",
        ),
        (
            "Strong: very strong thermals",
            dict(thermal_quality_pct=100, updraft_ms=r.thermal_strong_updraft_ms),
            "strong",
        ),
        (
            "Good: strong thermals with a brisk wind are still only Good",
            dict(thermal_quality_pct=80, updraft_ms=3.0, ground_kph=18, aloft_kph=18),
            "good",
        ),
        (
            "Good: strong thermals in a light wind",
            dict(thermal_quality_pct=90, updraft_ms=2.7, ground_kph=8),
            "good",
        ),
        (
            "Poor: thermals under the Ok quality",
            dict(thermal_quality_pct=r.thermal_ok_quality_pct - 1, updraft_ms=1.0),
            "poor",
        ),
        (
            "Strong never hides rain",
            dict(thermal_quality_pct=100, updraft_ms=3.0, rain_mm_h=r.rain_light_mm_h),
            "poor",
        ),
        (
            "Strong never hides a thunderstorm risk",
            dict(thermal_quality_pct=100, updraft_ms=3.0, cape_j_kg=r.cape_storm_j_kg),
            "bad",
        ),
        ("Poor: too light", dict(ground_kph=0.5, aloft_kph=0.5), "poor"),
        ("Poor: off direction (light wind)", dict(ground_dir=180), "poor"),
        ("Poor: weak thermals", dict(thermal_quality_pct=10), "poor"),
        ("Poor: low thermals", dict(thermal_height_m=r.thermal_min_height_m - 1), "poor"),
        ("Poor: rain", dict(rain_mm_h=r.rain_light_mm_h), "poor"),
        (
            "Bad (turbulent): wind at the orange band",
            dict(
                ground_kph=mph_to_kph(r.speed_orange_from_mph),
                aloft_kph=mph_to_kph(r.speed_orange_from_mph),
            ),
            "bad",
        ),
        ("Bad (turbulent): gusts", dict(gust_kph=mph_to_kph(r.gust_orange_from_mph)), "bad"),
        (
            "Crossed (just off direction) does not cap the grade",
            dict(ground_dir=r.sector_half_width_deg + 5),
            "good",
        ),
        (
            "Poor: beyond the margin",
            dict(ground_dir=r.sector_half_width_deg + r.marginal_margin_deg + 5),
            "poor",
        ),
        ("Bad (turbulent): storm energy, no rain", dict(cape_j_kg=r.cape_overdevelop_j_kg), "bad"),
        (
            "Bad (dangerous): wind at the red band",
            dict(
                ground_kph=mph_to_kph(r.speed_red_from_mph),
                aloft_kph=mph_to_kph(r.speed_red_from_mph),
            ),
            "bad",
        ),
        ("Bad (dangerous): gusts", dict(gust_kph=mph_to_kph(r.gust_red_from_mph)), "bad"),
        (
            "Bad (dangerous): strong wind well off direction",
            dict(
                ground_dir=180,
                ground_kph=mph_to_kph(r.speed_orange_from_mph),
                aloft_kph=mph_to_kph(r.speed_orange_from_mph),
            ),
            "bad",
        ),
        ("Bad (dangerous): heavy rain", dict(rain_mm_h=r.rain_heavy_mm_h), "bad"),
        ("Bad (dangerous): storm energy alone", dict(cape_j_kg=r.cape_storm_j_kg), "bad"),
        (
            "Bad (dangerous): moderate storm energy with rain",
            dict(cape_j_kg=r.cape_overdevelop_j_kg, rain_mm_h=r.rain_light_mm_h),
            "bad",
        ),
    ], base


def test_every_claim_in_the_guide_is_what_the_grading_does(rules):
    cases, base = claim_cases(rules)
    for name, change, expected in cases:
        kw = {**base, **change}
        verdict, _ = grade_block(rules=rules, **kw)
        assert verdict == expected, name


def test_worst_problem_sets_the_grade(rules):
    # calm, aligned wind but a thunderstorm risk: Bad, as the Guide says
    v, _ = grade_block(0, 3, 3, 90, 2000, rules, cape_j_kg=rules.cape_storm_j_kg)
    assert v == "bad"


def test_hang_glider_limits_are_the_ones_the_guide_quotes(rules):
    kph = mph_to_kph(rules.hg_speed_orange_from_mph)
    assert grade_block(0, kph, kph, 70, 1800, rules, "hg")[0] == "bad"
    just_under = mph_to_kph(rules.hg_speed_orange_from_mph) - 3  # and a gust-safe wind is not
    assert grade_block(0, just_under, just_under, 70, 1800, rules, "hg")[0] != "bad"
    kph = mph_to_kph(rules.hg_speed_red_from_mph)
    assert grade_block(0, kph, kph, 70, 1800, rules, "hg")[0] == "bad"


def test_shear_really_does_not_change_the_grade(rules):
    tz = timezone(timedelta(hours=11))
    t0 = datetime(2026, 10, 4, 11, tzinfo=tz)
    calm = build_block(t0, Wind(0, 8), Wind(0, 8), 1500, 250, 16, 800, rules, launch=Wind(0, 8))
    sheared = build_block(
        t0, Wind(0, 8), Wind(180, 8), 1500, 250, 16, 800, rules, launch=Wind(0, 8)
    )
    assert calm.shear == "light" and sheared.shear == "strong"
    assert calm.verdict_pg == sheared.verdict_pg  # shown, not graded


@pytest.mark.parametrize("word", ["Ok", "Good", "Strong", "Poor", "Bad"])
def test_each_grade_is_explained(fixture_path, site, rules, word):
    html = guide_html(fixture_path, site, rules)
    assert re.search(rf'<span class="pill {word.lower()}">.*?{word}</span>', html)


def test_guide_explains_what_thermal_height_means(fixture_path, site, rules):
    g = text(guide_html(fixture_path, site, rules))
    assert "about half the depth of the boundary layer above launch (not the top of it)" in g
    assert "launch height when the updraft is below" in g and "not usable" in g


def test_guide_critical_updraft_is_the_real_value_in_every_unit(fixture_path, site, rules):
    html = guide_html(fixture_path, site, rules)
    assert (
        "1.1 m/s" in html and "3.8 ft/sec" in html
    )  # 1.143 m/s (RASP's 225 ft/min critical value)


def test_the_thermal_height_claim_is_what_the_code_does(rules):
    from ffforecast.diagnostics import usable_thermal_height_asl

    launch = 800.0
    below = rules.critical_updraft_ms - 0.01
    assert usable_thermal_height_asl(1800, below, launch, rules) == launch  # "launch height"
    above = usable_thermal_height_asl(1800, rules.critical_updraft_ms, launch, rules)
    depth = above - launch
    assert 0.4 * 1800 <= depth <= 0.6 * 1800  # "about half the depth of the boundary layer"
    assert depth < 1800  # "not the top of it"
