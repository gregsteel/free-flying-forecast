"""Ok, Good and Strong: how the thermals split a block with no problems."""

import dataclasses

import pytest

from ffforecast.grading import grade_block
from ffforecast.units import mph_to_kph

ALL = {"ok", "good", "strong", "poor", "turbulent", "dangerous"}


def grade(rules, *, quality=90, updraft=2.7, wind=8.0, height=1500, glider="pg", **kw):
    """A block in the green sector with the given thermals; extra keywords add problems."""
    return grade_block(
        0, wind, wind, quality, height, rules, glider, kw.get("rain", 0), kw.get("cape", 0),
        kw.get("gust", 0), updraft_ms=updraft,
    )  # fmt: skip


def test_ok_good_and_strong_at_typical_values(rules):
    assert grade(rules, quality=50, updraft=1.2)[0] == "ok"
    assert grade(rules, quality=90, updraft=2.7)[0] == "good"
    assert grade(rules, quality=100, updraft=3.8)[0] == "strong"
    # the owner: an updraft of 1.7 m/s is not Good, however ok the quality
    assert grade(rules, quality=100, updraft=1.7)[0] == "ok"


def test_thermal_boundaries(rules):
    assert grade(rules, quality=39, updraft=1.0)[0] == "poor"  # under the ok quality
    assert grade(rules, quality=40, updraft=1.0)[0] == "ok"
    assert grade(rules, quality=70, updraft=2.49)[0] == "ok"  # strong enough only at 2.5 m/s
    assert grade(rules, quality=70, updraft=2.5)[0] == "good"
    assert grade(rules, quality=69, updraft=2.8)[0] == "ok"  # quality 70 is needed as well
    assert grade(rules, quality=100, updraft=3.49)[0] == "good"
    assert grade(rules, quality=100, updraft=3.5)[0] == "strong"


def test_low_thermals_are_poor_however_strong(rules):
    assert (
        grade(rules, quality=100, updraft=3.0, height=rules.thermal_min_height_m - 1)[0] == "poor"
    )


def test_a_brisk_wind_with_good_thermals_is_strong(rules):
    brisk = mph_to_kph(rules.strong_wind_from_mph)
    assert grade(rules, quality=80, updraft=2.7, wind=brisk)[0] == "strong"
    assert grade(rules, quality=80, updraft=2.7, wind=brisk - 0.5)[0] == "good"
    reasons = grade(rules, quality=80, updraft=2.7, wind=brisk)[1]
    assert any("brisk wind" in r and "Experienced pilots only" in r for r in reasons)


def test_a_brisk_wind_alone_is_not_strong(rules):
    brisk = mph_to_kph(rules.strong_wind_from_mph)
    assert grade(rules, quality=50, updraft=1.2, wind=brisk)[0] == "ok"  # thermals only decent
    assert (
        grade(rules, quality=60, updraft=1.7, wind=brisk)[0] == "ok"
    )  # quality under the good level


def test_hang_gliders_need_a_stronger_wind_for_strong(rules):
    wind = mph_to_kph(
        rules.strong_wind_from_mph + 0.5
    )  # brisk for a paraglider, not for a hang glider
    assert grade(rules, quality=80, updraft=2.7, wind=wind, glider="pg")[0] == "strong"
    assert grade(rules, quality=80, updraft=2.7, wind=wind, glider="hg")[0] == "good"
    hg_brisk = mph_to_kph(rules.hg_strong_wind_from_mph)
    assert grade(rules, quality=80, updraft=2.7, wind=hg_brisk, glider="hg")[0] == "strong"


def test_very_strong_thermals_are_strong_for_both_gliders(rules):
    for glider in ("pg", "hg"):
        assert grade(rules, quality=100, updraft=3.8, glider=glider)[0] == "strong"


# ---- ok thermals never hide a problem -------------------------------------------------------


@pytest.mark.parametrize(
    "problem,expected",
    [
        ({"rain": 0.3}, "poor"),
        ({"rain": 2.0}, "dangerous"),
        ({"cape": 600}, "turbulent"),
        ({"cape": 1500}, "dangerous"),
        ({"gust": mph_to_kph(17)}, "turbulent"),
        ({"gust": mph_to_kph(22)}, "dangerous"),
    ],
)
def test_strong_thermals_do_not_beat_rain_storms_or_gusts(rules, problem, expected):
    assert grade(rules, quality=100, updraft=3.0, **problem)[0] == expected


def test_strong_thermals_do_not_beat_a_wind_problem(rules):
    strong = mph_to_kph(rules.speed_orange_from_mph)
    assert grade(rules, quality=100, updraft=3.0, wind=strong)[0] == "turbulent"
    assert (
        grade_block(180, 8, 8, 100, 1500, rules, "pg", updraft_ms=3.0)[0] == "poor"
    )  # off direction, light


def test_every_result_is_one_of_the_six_grades(rules):
    for q in (0, 39, 40, 69, 70, 100):
        for u in (0.0, 1.0, 2.49, 2.5, 3.49, 3.5, 5.0):
            for w in (2, 8, 14, 17, 21, 30):
                for g in ("pg", "hg"):
                    assert grade(rules, quality=q, updraft=u, wind=w, glider=g)[0] in ALL


# ---- without an updraft value ---------------------------------------------------------------


def test_without_an_updraft_only_quality_decides_and_strong_is_unreachable(rules):
    assert grade_block(0, 8, 8, 90, 1500, rules)[0] == "good"
    assert grade_block(0, 8, 8, 50, 1500, rules)[0] == "ok"
    assert grade_block(0, 8, 8, 20, 1500, rules)[0] == "poor"
    assert (
        grade_block(0, mph_to_kph(rules.strong_wind_from_mph), 8, 100, 1500, rules)[0] != "strong"
    )


# ---- the reasons ------------------------------------------------------------------------------


def test_each_tier_explains_itself(rules):
    assert any("Decent thermals" in r for r in grade(rules, quality=50, updraft=1.2)[1])
    assert any("a time to go flying" in r for r in grade(rules, quality=90, updraft=2.7)[1])
    strong = grade(rules, quality=100, updraft=3.8)[1]
    assert any(
        "Powerful thermals (3.8 m/s)" in r and "Experienced pilots only" in r for r in strong
    )


# ---- thresholds are configuration ------------------------------------------------------------


def test_the_tier_thresholds_are_tunable(rules):
    stricter = dataclasses.replace(rules, thermal_strong_updraft_ms=4.2)
    assert grade(rules, quality=100, updraft=3.8)[0] == "strong"
    assert grade(stricter, quality=100, updraft=3.8)[0] == "good"
    easier = dataclasses.replace(rules, thermal_good_updraft_ms=1.2, thermal_good_quality_pct=50)
    assert grade(rules, quality=60, updraft=1.3)[0] == "ok"
    assert grade(easier, quality=60, updraft=1.3)[0] == "good"
