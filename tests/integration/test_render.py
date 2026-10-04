import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def load(fixture_path):
    return Forecast.from_dict(json.loads(fixture_path.read_text()))


def test_page_small_and_complete(fixture_path, site, rules):
    html = render_page(load(fixture_path), site, rules)
    assert len(html.encode()) < 200_000
    for day in ("Sun", "Mon", "Tue"):
        assert f"<strong>{day}</strong>" in html
    assert html.count('<table class="dt">') == 4
    assert "Low confidence" in html


def test_every_verdict_has_text_not_just_colour(fixture_path, site, rules):
    html = render_page(load(fixture_path), site, rules)
    for label in ("Good", "Poor", "Turbulent", "Dangerous"):
        assert f"{label}</a>" in html  # the grade word appears on the grade pills


def test_no_external_images_and_single_enhancement_script(fixture_path, site, rules):
    html = render_page(load(fixture_path), site, rules)
    imgs = re.findall(r"<img\s[^>]*>", html)  # only the station charts are images
    history = [i for i in imgs if 'class="history"' in i]
    assert len(history) == 5 and all("freeflightwx.com" in i for i in history)
    assert len(imgs) == 6  # plus the default period's no-script fallback
    assert all(" src=" not in i for i in history)  # nothing is fetched until the chart is wanted
    scripts = re.findall(r"<script[^>]*>", html)
    # only our two small scripts: the early settings one and the main enhancement one
    assert scripts == ['<script id="prefs">', '<script id="enhance">']
    assert "url(" not in html


def load_html(fixture_path, site, rules):
    return render_page(load(fixture_path), site, rules)


def test_dst_start_handled(fixture_path, site, rules):
    # 2026-10-04 is the first day of AEDT; blocks must still read 11:00..17:00 local
    html = render_page(load(fixture_path), site, rules)
    assert "11:00" in html and "17:00" in html


def test_station_chart_has_alt_text_and_links(fixture_path, site, rules):
    html = load_html(fixture_path, site, rules)
    assert 'alt="Wind speed and direction at the Mystic weather station' in html
    assert 'href="https://www.freeflightwx.com/mystic/4hours.php"' in html
    assert "windgraph.php?time=14400" in html and 'data-src="' in html
    assert html.count("<iframe") == 1  # only the club's cropped gauge; the charts are images


def test_current_conditions_tile_is_optional(fixture_path, site, rules):
    html = load_html(fixture_path, site, rules)
    assert '<section id="now" hidden' in html  # hidden until the script fills it
    assert "api.open-meteo.com" in html and '"lat": -36.7584099' in html
    assert "catch(function" in html  # failure leaves the tile hidden
