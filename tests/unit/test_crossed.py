"""A crossed launch (wind just outside the green sector) is noted, not a cap on the grade."""

import pytest

from ffforecast.grading import grade_block

CROSSED = 313  # 7 degrees past the 320 degree edge of the sector
BEYOND = 250  # well outside the margin


@pytest.mark.parametrize("updraft, grade", [(0, "poor"), (2, "ok"), (3, "good"), (4, "strong")])
def test_a_crossed_launch_is_graded_on_the_thermals(rules, updraft, grade):
    quality = 0 if updraft == 0 else 100
    v, reasons = grade_block(
        CROSSED, 8, 8, quality, 1900, rules, updraft_ms=float(updraft),
        good_updraft_ms=rules.ausrasp_good_updraft_ms,
        strong_updraft_ms=rules.ausrasp_strong_updraft_ms,
    )  # fmt: skip
    assert v == grade
    assert any("crossed" in r for r in reasons)  # still noted


def test_crossed_and_in_the_sector_grade_the_same(rules):
    a = grade_block(CROSSED, 8, 8, 100, 1900, rules, updraft_ms=3.0)[0]
    b = grade_block(0, 8, 8, 100, 1900, rules, updraft_ms=3.0)[0]
    assert a == b == "good"


def test_beyond_the_margin_is_still_poor_or_dangerous(rules):
    assert grade_block(BEYOND, 8, 8, 100, 1900, rules, updraft_ms=3.0)[0] == "poor"
    assert grade_block(BEYOND, 22, 22, 100, 1900, rules, updraft_ms=3.0)[0] in (
        "turbulent",
        "dangerous",
    )


def test_other_problems_still_win_over_a_crossed_launch(rules):
    assert grade_block(CROSSED, 25, 25, 100, 1900, rules, updraft_ms=3.0)[0] in (
        "turbulent",
        "dangerous",
    )  # strong wind
    assert (
        grade_block(CROSSED, 8, 8, 100, 1900, rules, gust_kph=30.0, updraft_ms=3.0)[0]
        == "turbulent"
    )
    assert (
        grade_block(CROSSED, 8, 8, 100, 1900, rules, rain_mm_h=2.0, updraft_ms=3.0)[0]
        == "dangerous"
    )


def test_the_guide_no_longer_lists_direction_under_turbulent(fixture_path, site, rules):
    import json
    import re

    from ffforecast.models import Forecast
    from ffforecast.render import render_page

    html = render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)
    m = re.search(r'<li id="guide-turbulent".*?</li>', html, flags=re.S)
    assert m is not None
    assert "direction" not in m.group(0)


def test_the_reason_and_the_guide_both_say_marginally_crossed(rules, fixture_path, site):
    import json
    import re

    from ffforecast.grading import grade_direction
    from ffforecast.models import Forecast
    from ffforecast.render import render_page

    assert "marginally crossed" in grade_direction(CROSSED, 8, rules)[1]
    html = render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)
    text = re.sub(r"<[^>]+>", " ", html)
    assert "which is marginally crossed: you can usually still get off" in text
    assert "amber just outside it (marginally crossed: noted" in text
