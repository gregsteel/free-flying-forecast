import dataclasses

from ffforecast.grading import grade_block, grade_direction, grade_speed
from ffforecast.units import mph_to_kph


def test_green_requires_direction_and_speed(rules):
    v, _ = grade_block(350, 12, 14, 70, 1500, rules)
    assert v == "good"


def test_speed_boundaries_in_mph(rules):
    assert grade_speed(mph_to_kph(11.9), rules)[0] == "ok"
    assert grade_speed(mph_to_kph(12), rules)[0] == "turbulent"
    assert grade_speed(mph_to_kph(13.9), rules)[0] == "turbulent"
    assert grade_speed(mph_to_kph(14), rules)[0] == "dangerous"
    assert grade_speed(0.5, rules)[0] == "poor"  # too light


def test_direction_sector(rules):
    assert grade_direction(0, 10, rules)[0] == "ok"
    assert grade_direction(40, 10, rules)[0] == "ok"
    assert grade_direction(320, 10, rules)[0] == "ok"
    assert grade_direction(41, 10, rules)[0] == "ok"  # marginal: crossed, noted, not limiting
    assert "crossed" in grade_direction(41, 10, rules)[1]
    assert grade_direction(70, 10, rules)[0] == "ok" and grade_direction(71, 10, rules)[0] == "poor"
    assert grade_direction(120, 10, rules)[0] == "poor"
    assert grade_direction(120, 25, rules)[0] == "dangerous"


def test_wrong_direction_is_never_good(rules):
    v, reasons = grade_block(180, 10, 10, 90, 2000, rules)
    assert v != "good" and any("sector" in r for r in reasons)


def test_weak_thermals_make_poor(rules):
    v, reasons = grade_block(0, 10, 10, 10, 1500, rules)
    assert v == "poor" and any("Thermals" in r for r in reasons)


def test_aloft_wind_counts(rules):
    v, reasons = grade_block(0, 10, mph_to_kph(15), 90, 2000, rules)
    assert v == "bad" and any(r.startswith("Aloft") for r in reasons)


def test_hang_gliders_graded_separately(rules):
    kph = mph_to_kph(13)  # over the paraglider limit (12 mph), under the hang glider's (14)
    pg, _ = grade_block(0, kph, kph, 90, 2000, rules, "pg")
    hg, _ = grade_block(0, kph, kph, 90, 2000, rules, "hg")
    assert pg == "bad" and hg == "good"


def test_reasons_always_present(rules):
    _, reasons = grade_block(0, 10, 10, 90, 2000, rules)
    assert reasons


def test_threshold_change_changes_verdict(rules):
    stricter = dataclasses.replace(rules, speed_orange_from_mph=5, speed_red_from_mph=20)
    assert grade_block(0, 12, 12, 90, 2000, rules)[0] == "good"
    assert grade_block(0, 12, 12, 90, 2000, stricter)[0] == "bad"
