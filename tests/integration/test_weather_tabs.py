"""The "Today" panel has a tab per place: Mystic, Mt Hotham, and any added in the site file."""

import dataclasses
import json
import re
from pathlib import Path

import pytest

from ffforecast.config import ConfigError, load_site
from ffforecast.models import Forecast
from ffforecast.render import render_page

ROOT = Path(__file__).resolve().parents[2]


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def panel(html):
    return html[
        html.index('<section id="now"') : html.index('<section aria-label="Weather station">')
    ]


def test_the_site_file_defines_mystic_and_mt_hotham(site):
    ids = [t["id"] for t in site.weather_tabs]
    assert ids == ["mystic", "hotham"]
    hotham = site.weather_tabs[1]
    assert (hotham["lat"], hotham["lon"], hotham["elevation_m"]) == (-36.97528, 147.13278, 1862.0)
    assert site.weather_tabs[0]["lat"] == site.lat  # a tab without a position uses the site's
    assert "Mt Hotham" in hotham["note"] and "marginal" in hotham["note"]


def test_the_panel_has_a_tab_for_each_place_with_mystic_first_and_selected(
    fixture_path, site, rules
):
    p = panel(page(fixture_path, site, rules))
    assert re.findall(r'<input type="radio" name="wx" id="wx-([a-z]+)"( checked)?>', p) == [
        ("mystic", " checked"),
        ("hotham", ""),
    ]
    assert '<label for="wx-mystic">Mystic</label>' in p
    assert '<label for="wx-hotham">Mt Hotham</label>' in p
    assert "Today at Mystic" in p and "Today at Mt Hotham" in p


def test_each_tab_has_its_own_current_conditions_and_hourly_table(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    p = panel(html)
    for place in ("mystic", "hotham"):
        for part in (
            "now-icon",
            "now-text",
            "now-temp",
            "now-wind",
            "now-gust",
            "now-rain",
            "now-note",
        ):
            assert f'id="{part}-{place}"' in p
        assert f'id="today-rows-{place}"' in p
    assert p.count('<table class="today"') == 2
    assert "Forecast for the rest of today: Mt Hotham" in p


def test_only_the_chosen_tab_is_shown(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert ".wx{display:none}" in html
    for place in ("mystic", "hotham"):
        assert f"body:has(#wx-{place}:checked) div.wx-{place}{{display:block}}" in html
        assert f"body:has(#wx-{place}:checked) span.wx-{place}{{display:inline}}" in html


def test_the_hotham_tab_carries_the_owners_note(fixture_path, site, rules):
    p = panel(page(fixture_path, site, rules))
    assert '<p class="tabnote">Strong wind at Mt Hotham might indicate Mystic is marginal.</p>' in p
    assert p.count('class="tabnote"') == 1  # Mystic has no note


def test_the_script_fetches_every_tab_with_its_own_position_and_elevation(
    fixture_path, site, rules
):
    html = page(fixture_path, site, rules)
    m = re.search(r"var TABS=(\[.*?\]);", html)
    assert m is not None
    tabs = json.loads(m.group(1).replace("\\u0027", "'"))
    assert [t["id"] for t in tabs] == ["mystic", "hotham"]
    assert tabs[0]["lat"] == -36.7584099 and tabs[0]["elevation_m"] is None
    assert tabs[1]["lat"] == -36.97528 and tabs[1]["elevation_m"] == 1862
    assert 'latitude="+tab.lat+"&longitude="+tab.lon' in html
    assert '(tab.elevation_m!==null?"&elevation="+tab.elevation_m:"")' in html
    assert "function tiles(){for(var i=0;i<TABS.length;i++){tile(TABS[i]);}}" in html


def test_the_chosen_tab_is_remembered_with_the_other_settings(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    # the settings script keeps every radio group on the page, so the place is saved like the rest
    assert 'name="wx"' in html and "input[type=radio]" in html


def test_a_single_tab_shows_no_tab_bar(fixture_path, site, rules):
    one = dataclasses.replace(site, weather_tabs=site.weather_tabs[:1])
    p = panel(page(fixture_path, one, rules))
    assert 'name="wx"' not in p and 'class="periods"' not in p
    assert "Today at Mystic" in p and "Hotham" not in p


def test_a_third_tab_is_just_more_configuration(fixture_path, site, rules):
    tabs = site.weather_tabs + (
        {"id": "falls", "label": "Falls Creek", "heading": "Today at Falls Creek", "lat": -36.86,
         "lon": 147.28, "elevation_m": 1600.0, "note": ""},
    )  # fmt: skip
    p = panel(page(fixture_path, dataclasses.replace(site, weather_tabs=tabs), rules))
    assert 'id="wx-falls"' in p and 'id="today-rows-falls"' in p and "Today at Falls Creek" in p


def test_with_no_tabs_configured_there_is_one_for_the_site(tmp_path):
    text = (ROOT / "config/site.mystic.toml").read_text()
    a = text.index("[[weather_tabs]]")
    b = text.index("[[station_charts]]")
    f = tmp_path / "s.toml"
    f.write_text(text[:a] + text[b:])
    s = load_site(f)
    assert len(s.weather_tabs) == 1 and s.weather_tabs[0]["lat"] == s.lat


@pytest.mark.parametrize(
    "extra, message",
    [
        ('[[weather_tabs]]\nid = "x"\nlabel = "X"\n', "heading"),
        ('[[weather_tabs]]\nid = "x"\nlabel = "X"\nheading = "H"\nlat = 120\n', "out of range"),
        ('[[weather_tabs]]\nid = "a b"\nlabel = "X"\nheading = "H"\n', "id may only hold"),
    ],
)
def test_bad_tabs_are_rejected(tmp_path, extra, message):
    text = (ROOT / "config/site.mystic.toml").read_text()
    a = text.index("[[weather_tabs]]")
    f = tmp_path / "s.toml"
    f.write_text(text[:a] + extra + "\n" + text[a:])
    with pytest.raises(ConfigError, match=message):
        load_site(f)


def test_duplicate_tab_ids_are_rejected(tmp_path):
    text = (ROOT / "config/site.mystic.toml").read_text()
    f = tmp_path / "s.toml"
    f.write_text(text.replace('id = "hotham"', 'id = "mystic"'))
    with pytest.raises(ConfigError, match="unique"):
        load_site(f)


def test_each_tab_links_to_the_bureau_of_meteorology_without_fetching_anything(
    fixture_path, site, rules
):
    html = page(fixture_path, site, rules)
    p = panel(html)
    links = re.findall(
        r'<p class="tablink"><a href="([^"]+)" target="_blank" rel="noopener noreferrer">([^<]+)</a></p>',
        p,
    )
    assert links == [
        (
            "https://www.bom.gov.au/places/vic/bright/",
            "Bureau of Meteorology: Bright forecast and observations",
        ),
        (
            "https://www.bom.gov.au/products/IDV60801/IDV60801.94906.shtml",
            "Bureau of Meteorology: measured observations at Mount Hotham",
        ),
    ]
    # a link only: the page's own scripts never ask the Bureau for anything (its terms forbid scraping)
    script = html[html.index("var TABS=") :]
    assert "bom.gov.au" not in script.split("</script>")[0]


def test_a_link_needs_both_a_label_and_an_https_address(tmp_path):
    text = (ROOT / "config/site.mystic.toml").read_text()
    for bad, message in (
        ('link_label = "Bureau of Meteorology: Bright forecast and observations"\n', "go together"),
    ):
        f = tmp_path / "s.toml"
        f.write_text(text.replace(bad, "", 1))
        with pytest.raises(ConfigError, match=message):
            load_site(f)
    f = tmp_path / "s2.toml"
    f.write_text(
        text.replace(
            'link_url = "https://www.bom.gov.au/places/vic/bright/"',
            'link_url = "http://www.bom.gov.au/x"',
        )
    )
    with pytest.raises(ConfigError, match="https"):
        load_site(f)
