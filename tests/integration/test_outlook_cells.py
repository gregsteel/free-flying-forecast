import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def page(fixture_path, site, rules, mutate=None):
    d = json.loads(fixture_path.read_text())
    if mutate:
        mutate(d)
    return render_page(Forecast.from_dict(d), site, rules)


def outlook_of(html):
    return html[html.index('<div class="outlook">') : html.index('<details class="guide"')]


def day_cells(html):
    row = re.findall(r'<details class="day"[^>]*>.*?</summary>', html, flags=re.S)[0]
    return row


def test_outlook_uses_the_same_box_icon_and_wind_markup_as_the_day_cells(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    out, row = outlook_of(html), day_cells(html)
    for cls in (
        'class="cell ',
        'class="ctime"',
        'class="cicon g g-pg"',
        'class="clw"',
        'class="dir ',
    ):
        assert cls in out and cls in row  # one set of fonts and sizes for both
    assert 'class="pill' not in out  # no text pills any more: the same large icon as the day boxes


def test_outlook_days_show_a_wind_arrow_with_direction_and_speed(fixture_path, site, rules):
    out = outlook_of(page(fixture_path, site, rules))
    cells = re.findall(r'<section class="cell.*?</section>', out, flags=re.S)
    assert len(cells) == 3
    for c in cells:
        assert 'class="dir ' in c and "<svg" in c and "transform:rotate(" in c
        assert re.search(
            r"</span> (N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW) <span", c
        )  # text too


def test_outlook_arrow_colours_follow_the_flyable_direction(fixture_path, site, rules):
    out = outlook_of(page(fixture_path, site, rules))
    # fixture winds: 200 degrees (off), 10 degrees (inside the sector), 340 degrees (inside)
    classes = re.findall(r'<span class="dir (ok|marginal|off)"', out)
    assert classes == ["off", "ok", "ok"]


def test_outlook_arrows_point_the_way_the_wind_blows(fixture_path, site, rules):
    out = outlook_of(page(fixture_path, site, rules))
    assert re.findall(r"transform:rotate\((\d+)deg\)", out) == ["200", "10", "340"]


def test_outlook_still_flags_rain_and_follows_the_glider(fixture_path, site, rules):
    out = outlook_of(page(fixture_path, site, rules))
    assert out.count('class="cwet"') == 1  # only the wet day
    assert 'class="cicon g g-hg"' in out and "What does this grade mean?" in out


def test_every_arrow_comes_from_one_macro(fixture_path, site, rules):
    tpl = open("templates/page.html.j2").read()
    assert (
        tpl.count("M10 18.5 3.5 3.5h13z") == 1
    )  # defined once, used by the day boxes and the outlook
    assert "{% macro arrow(" in tpl


def test_weather_station_heading(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    # the heading is just a link to the station (the owner dropped the period, "last 4 hours")
    assert (
        '<h2><a href="https://www.freeflightwx.com/mystic/index.php">FreeFlight WX</a></h2>' in html
    )
    assert "<h2>Station: " not in html and "<h2>Weather Station: " not in html
    assert "last 4 hours</span>" not in html


def test_pinned_header_has_a_break_below_it(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    m = re.search(r"\.sticky\{position:sticky;[^}]*\}", html)
    assert m is not None
    css = m.group(0)
    assert "padding:.6rem 1rem .9rem" in css  # room under the alert before the content starts
    assert "border-bottom:1px solid var(--line)" in css and "box-shadow:" in css  # a clear edge
