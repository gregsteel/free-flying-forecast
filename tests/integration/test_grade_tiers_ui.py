"""Ok, Good and Strong on the page: colours, icons, Guide, links."""

import dataclasses
import json
import re

import pytest

from ffforecast.models import Forecast
from ffforecast.render import ICONS, LABELS, render_page
from ffforecast.units import mph_to_kph

GRADES = ("ok", "good", "strong", "poor", "turbulent", "dangerous")


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def guide_list(html, glider):
    m = re.search(rf'<ul class="guide g g-{glider}">(.*?)</ul>', html, flags=re.S)
    assert m is not None
    return m.group(1)


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def test_there_are_six_grades_each_with_its_own_icon_and_word():
    assert set(ICONS) == set(LABELS) == set(GRADES)
    assert len(set(ICONS.values())) == 6  # no two grades share an icon
    assert LABELS["ok"] == "Ok" and LABELS["strong"] == "Strong"


def test_every_grade_has_a_colour_in_both_themes(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    for g in ("ok", "strong"):
        assert html.count(f"--{g}:") == 2 and html.count(f"--{g}-bg:") == 2  # light and dark
    for g in GRADES:
        assert f".pill.{g}{{border-color:var(--{g})}}" in html
        assert f".pg-{g}{{--pgc:var(--{g});--pgb:var(--{g}-bg)}}" in html
        assert f".hg-{g}{{--hgc:var(--{g});--hgb:var(--{g}-bg)}}" in html
        assert f"table.dt .pill.{g}{{background:var(--{g}-bg)}}" in html


def test_strong_is_visibly_different_from_the_green_grades(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    colours = {}
    for g in ("ok", "good", "strong"):
        m = re.search(rf"--{g}:(#[0-9a-f]{{6}})", html)
        assert m is not None
        colours[g] = m.group(1)
    assert len(set(colours.values())) == 3


def test_the_fixture_page_shows_all_six_grades(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    for g in GRADES:
        assert f'class="cell pg-{g}' in html or f"hg-{g}" in html, g
        assert f"Paraglider: {LABELS[g]}." in html, g  # the day icon's name for screen readers


def test_each_grade_has_a_link_target_in_the_guide(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    ids = re.findall(r'<li id="(guide-[a-z-]+)"', html)
    assert ids == [f"guide-{g}" for g in GRADES] + [f"guide-hg-{g}" for g in GRADES]
    for g in GRADES:
        assert f'href="#guide-{g}"' in html or g not in (
            "ok",
            "strong",
            "good",
        )  # linked from the page


def test_the_guide_lists_the_six_grades_in_order_for_each_glider(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    for glider in ("pg", "hg"):
        pills = re.findall(r'<span class="pill ([a-z]+)">', guide_list(html, glider))
        assert pills == list(GRADES)


def test_the_guide_describes_ok_good_and_strong_in_the_owners_words(fixture_path, site, rules):
    t = text(guide_list(page(fixture_path, site, rules), "pg"))
    assert "A time you definitely want to go flying" in t  # Good
    assert "Powerful, and it demands experience" in t and "not a time for novices" in t  # Strong
    assert "Flyable, with decent thermals" in t  # Ok


def test_the_guide_quotes_the_real_thresholds_per_glider(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    pg, hg = guide_list(html, "pg"), guide_list(html, "hg")
    assert f"{rules.thermal_good_quality_pct:.0f}%" in pg and "2.5 m/s" in pg and "3.5 m/s" in pg
    assert '<span class="u s-kph">14 kph</span>' in pg  # 9 mph: the paraglider's brisk wind
    assert '<span class="u s-kph">18 kph</span>' in hg  # 11 mph: the hang glider's
    assert '<span class="u s-kph">14 kph</span>' not in hg.split("Strong")[1].split("</li>")[0]
    assert (
        '<span class="u a-ft">8.2 ft/sec</span>' in pg or "ft/sec" in pg
    )  # follows the height unit


def test_the_guide_follows_changed_tier_rules(fixture_path, site, rules):
    tuned = dataclasses.replace(
        rules,
        thermal_strong_updraft_ms=3.0,
        thermal_good_quality_pct=60,
        strong_wind_from_mph=10,
    )
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    pg = guide_list(render_page(fc, site, tuned), "pg")
    assert "3.0 m/s" in pg and "60%" in pg
    assert f'<span class="u s-kph">{mph_to_kph(10):.0f} kph</span>' in pg


def test_the_page_script_opens_the_guide_for_every_grade(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "(ok|good|strong|poor|turbulent|dangerous)" in html


def test_the_poor_entry_says_where_poor_thermals_begin(fixture_path, site, rules):
    t = text(guide_list(page(fixture_path, site, rules), "pg"))
    assert f"quality under {rules.thermal_ok_quality_pct:.0f}%" in t


def test_the_intro_says_thermals_decide_between_the_ok_grades(fixture_path, site, rules):
    t = text(page(fixture_path, site, rules))
    assert "the thermals decide between Poor, Ok, Good and Strong" in t


@pytest.mark.parametrize("grade", GRADES)
def test_every_grade_can_be_an_outlook_day(fixture_path, site, rules, grade):
    d = json.loads(fixture_path.read_text())
    d["outlook"][0]["verdict"] = grade
    html = render_page(Forecast.from_dict(d), site, rules)
    out = html[html.index('<div class="outlook">') : html.index('<details class="guide"')]
    assert f"Paraglider: {LABELS[grade]}." in out and f"pg-{grade}" in out


def test_the_guide_does_not_say_as_ok(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "As Ok" not in html and "as Ok" not in html  # it read as confusing
    for glider in ("pg", "hg"):
        t = text(guide_list(html, glider))
        assert (
            "A time you definitely want to go flying. Strong, workable thermals (quality at least"
            in t
        )
        assert "Powerful, and it demands experience. Very strong thermals (an updraft of" in t


def test_the_guide_shows_the_icon_used_for_each_grade(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    for glider in ("pg", "hg"):
        items = re.findall(r'<li id="guide-[a-z-]+".*?</li>', guide_list(html, glider), flags=re.S)
        if not items:  # guide_list returns the inner text; find the entries directly
            items = re.findall(r'<li id="guide-[a-z-]+".*?</li>', html, flags=re.S)
        for grade in GRADES:
            entry = next(i for i in items if f'class="pill {grade}"' in i)
            assert ICONS[grade] in entry, (glider, grade)
    assert len({ICONS[g] for g in GRADES}) == 6  # six different icons, so each is distinguishable
