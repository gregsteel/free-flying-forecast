"""Ok, Good and Strong: how the thermals split a block with no problems."""

import dataclasses

import pytest

from ffforecast.grading import grade_block
from ffforecast.units import mph_to_kph

ALL = {"ok", "good", "strong", "poor", "bad"}


def grade(rules, *, quality=90, updraft=2.7, wind=8.0, height=1500, glider="pg", **kw):
    """A block in the green sector with the given thermals; extra keywords add problems."""
    return grade_block(
        0, wind, wind, quality, height, rules, glider, kw.get("rain", 0), kw.get("cape", 0),
        kw.get("gust", 0), updraft_ms=updraft,
    )  # fmt: skip


def test_ok_good_and_strong_at_typical_values(rules):
    assert grade(rules, quality=50, updraft=1.2)[0] == "ok"
    assert grade(rules, quality=90, updraft=2.7)[0] == "good"
    assert grade(rules, quality=100, updraft=4.2)[0] == "strong"
    # the owner: an updraft of 1.7 m/s is not Good, however ok the quality
    assert grade(rules, quality=100, updraft=1.7)[0] == "ok"


def test_thermal_boundaries(rules):
    assert grade(rules, quality=39, updraft=1.0)[0] == "poor"  # under the ok quality
    assert grade(rules, quality=40, updraft=1.0)[0] == "ok"
    assert grade(rules, quality=70, updraft=2.49)[0] == "ok"  # strong enough only at 2.5 m/s
    assert grade(rules, quality=70, updraft=2.5)[0] == "good"
    assert grade(rules, quality=69, updraft=2.8)[0] == "ok"  # quality 70 is needed as well
    assert grade(rules, quality=100, updraft=3.99)[0] == "good"
    assert grade(rules, quality=100, updraft=4.0)[0] == "strong"  # the owner: 4 before it is Strong


def test_low_thermals_are_poor_however_strong(rules):
    assert (
        grade(rules, quality=100, updraft=3.0, height=rules.thermal_min_height_m - 1)[0] == "poor"
    )


def test_a_brisk_wind_does_not_make_good_thermals_strong(rules):
    """The owner (2026-10-05): a block with 3 m/s thermals and a brisk wind was graded Strong. Only an
    updraft of 4 m/s makes it Strong, whatever the wind."""
    for wind in (8, 14, 18):
        assert grade(rules, quality=80, updraft=3.0, wind=wind)[0] == "good"
        assert grade(rules, quality=80, updraft=3.0, wind=wind, glider="hg")[0] == "good"


def test_a_brisk_wind_alone_is_not_strong(rules):
    assert grade(rules, quality=50, updraft=1.2, wind=14)[0] == "ok"  # thermals only decent
    assert grade(rules, quality=60, updraft=1.7, wind=14)[0] == "ok"  # quality under the good level


def test_the_ausrasp_updraft_must_be_4_for_strong(rules):
    kw = {
        "good_updraft_ms": rules.ausrasp_good_updraft_ms,
        "strong_updraft_ms": rules.ausrasp_strong_updraft_ms,
    }
    assert rules.ausrasp_strong_updraft_ms == 4 and rules.thermal_strong_updraft_ms == 4
    assert grade_block(0, 10, 10, 100, 1700, rules, updraft_ms=3, **kw)[0] == "good"
    assert grade_block(0, 10, 10, 100, 1700, rules, updraft_ms=4, **kw)[0] == "strong"


def test_very_strong_thermals_are_strong_for_both_gliders(rules):
    for glider in ("pg", "hg"):
        assert grade(rules, quality=100, updraft=4.2, glider=glider)[0] == "strong"


# ---- ok thermals never hide a problem -------------------------------------------------------


@pytest.mark.parametrize(
    "problem,expected",
    [
        ({"rain": 0.3}, "poor"),
        ({"rain": 2.0}, "bad"),
        ({"cape": 600}, "bad"),
        ({"cape": 1500}, "bad"),
        ({"gust": mph_to_kph(17)}, "bad"),
        ({"gust": mph_to_kph(22)}, "bad"),
    ],
)
def test_strong_thermals_do_not_beat_rain_storms_or_gusts(rules, problem, expected):
    assert grade(rules, quality=100, updraft=3.0, **problem)[0] == expected


def test_strong_thermals_do_not_beat_a_wind_problem(rules):
    strong = mph_to_kph(rules.speed_orange_from_mph)
    assert grade(rules, quality=100, updraft=3.0, wind=strong)[0] == "bad"
    assert (
        grade_block(180, 8, 8, 100, 1500, rules, "pg", updraft_ms=3.0)[0] == "poor"
    )  # off direction, light


def test_every_result_is_one_of_the_five_grades(rules):
    for q in (0, 39, 40, 69, 70, 100):
        for u in (0.0, 1.0, 2.49, 2.5, 3.99, 4.0, 5.0):
            for w in (2, 8, 14, 17, 21, 30):
                for g in ("pg", "hg"):
                    assert grade(rules, quality=q, updraft=u, wind=w, glider=g)[0] in ALL


# ---- without an updraft value ---------------------------------------------------------------


def test_without_an_updraft_only_quality_decides_and_strong_is_unreachable(rules):
    assert grade_block(0, 8, 8, 90, 1500, rules)[0] == "good"
    assert grade_block(0, 8, 8, 50, 1500, rules)[0] == "ok"
    assert grade_block(0, 8, 8, 20, 1500, rules)[0] == "poor"
    assert grade_block(0, 14, 8, 100, 1500, rules)[0] != "strong"


# ---- the reasons ------------------------------------------------------------------------------


def test_each_tier_explains_itself(rules):
    assert any("Decent thermals" in r for r in grade(rules, quality=50, updraft=1.2)[1])
    assert any("a time to go flying" in r for r in grade(rules, quality=90, updraft=2.7)[1])
    strong = grade(rules, quality=100, updraft=4.2)[1]
    assert any(
        "Powerful thermals (4.2 m/s)" in r and "Experienced pilots only" in r for r in strong
    )


# ---- thresholds are configuration ------------------------------------------------------------


def test_the_tier_thresholds_are_tunable(rules):
    stricter = dataclasses.replace(rules, thermal_strong_updraft_ms=4.5)
    assert grade(rules, quality=100, updraft=4.2)[0] == "strong"
    assert grade(stricter, quality=100, updraft=4.2)[0] == "good"
    easier = dataclasses.replace(rules, thermal_good_updraft_ms=1.2, thermal_good_quality_pct=50)
    assert grade(rules, quality=60, updraft=1.3)[0] == "ok"
    assert grade(easier, quality=60, updraft=1.3)[0] == "good"
