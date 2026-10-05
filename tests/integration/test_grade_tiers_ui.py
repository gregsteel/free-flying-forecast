"""Ok, Good and Strong on the page: colours, icons, Guide, links."""

import dataclasses
import json
import re

import pytest

from ffforecast.models import Forecast
from ffforecast.render import ICONS, LABELS, render_page

GRADES = ("ok", "good", "strong", "poor", "bad")


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def guide_list(html, glider):
    m = re.search(rf'<ul class="guide g g-{glider}">(.*?)</ul>', html, flags=re.S)
    assert m is not None
    return m.group(1)


def text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def test_there_are_five_grades_each_with_its_own_icon_and_word():
    assert set(ICONS) == set(LABELS) == set(GRADES)
    assert len(set(ICONS.values())) == 5  # no two grades share an icon
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


def test_the_fixture_page_shows_all_five_grades(fixture_path, site, rules):
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


def test_the_guide_lists_the_five_grades_in_order_for_each_glider(fixture_path, site, rules):
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
    assert f"{rules.thermal_good_quality_pct:.0f}%" in pg and "2.5 m/s" in pg and "4.0 m/s" in pg
    assert "brisk" not in pg and "brisk" not in hg  # a brisk wind no longer makes a block Strong
    assert "Nothing else makes a block Strong" in pg
    assert (
        '<span class="u a-ft">8.2 ft/sec</span>' in pg or "ft/sec" in pg
    )  # follows the height unit


def test_the_guide_follows_changed_tier_rules(fixture_path, site, rules):
    tuned = dataclasses.replace(
        rules,
        thermal_strong_updraft_ms=3.0,
        thermal_good_quality_pct=60,
    )
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    pg = guide_list(render_page(fc, site, tuned), "pg")
    assert "3.0 m/s" in pg and "60%" in pg


def test_the_page_script_opens_the_guide_for_every_grade(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "(ok|good|strong|poor|bad)" in html


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
            "A time you definitely want to go flying. Good, workable thermals (quality at least"
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
    assert len({ICONS[g] for g in GRADES}) == 5  # five different icons, so each is distinguishable


# ---- icons and the sun indicator (owner, 2026-10-05) ---------------------------------------------


def test_poor_is_a_sideways_thumb_and_bad_a_thumbs_down(fixture_path, site, rules):
    from ffforecast.render import ICONS

    assert str(ICONS["poor"]) == '<span class="sideways">\U0001f44d</span>'  # the thumbs-up, turned
    assert ICONS["bad"] == "\U0001f44e"
    assert ICONS["good"] == "\U0001f44d" and ICONS["poor"] != ICONS["good"]
    html = page(fixture_path, site, rules)
    assert ".sideways{display:inline-block;transform:rotate(-90deg)}" in html
    assert (
        "\U0001f7e1" not in html and "\U0001f7e0" not in html
    )  # the old yellow and orange circles
    for grade in ("poor", "bad"):
        entry = guide_list(html, "pg").split(f'id="guide-{grade}"')[1].split("</li>")[0]
        assert str(ICONS[grade]) in entry


def test_the_sun_indicator_follows_the_rules_thresholds(rules):
    from ffforecast.render import SUN_PARTLY, SUN_SHADED, SUN_SUNNY, sun_indicator

    assert sun_indicator(None, rules) == ("", "")
    assert sun_indicator(round(rules.sun_full_pct), rules)[0] == SUN_SUNNY
    assert sun_indicator(round(rules.sun_full_pct) - 1, rules)[0] == SUN_PARTLY
    assert sun_indicator(round(rules.sun_shaded_pct), rules)[0] == SUN_PARTLY
    icon, words = sun_indicator(round(rules.sun_shaded_pct) - 1, rules)
    assert icon == SUN_SHADED and "Mostly shaded" in words


def test_each_hourly_tile_shows_its_sun_or_shade(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    first = re.search(r'<details class="day">.*?</summary>', html, flags=re.S)
    assert first is not None
    tiles = re.findall(
        r'<span class="csun" role="img" aria-label="([^"]+)"[^>]*>(.)', first.group(0)
    )
    assert len(tiles) == 9  # one under each hour
    kinds = " ".join(t for t, _ in tiles)
    assert (
        "Sunny" in kinds and "Mostly shaded" in kinds
    )  # the fixture has both (poor hours are shaded)


def test_a_block_without_a_sun_figure_shows_no_indicator(fixture_path, site, rules):
    d = json.loads(fixture_path.read_text())
    for b in d["blocks"]:
        b["sun_pct"], b["sun_source"] = None, ""
    html = render_page(Forecast.from_dict(d), site, rules)
    assert 'class="csun"' not in html
    assert "not available" in html  # the detail row says so
