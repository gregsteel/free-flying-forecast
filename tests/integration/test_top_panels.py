import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def test_station_left_weather_right_on_wide_screens_and_weather_first_on_phones(
    fixture_path, site, rules
):
    html = page(fixture_path, site, rules)
    top = html[html.index('<div class="top">') : html.index("<h2>Days 5 to 7 outlook</h2>")]
    assert top.index('id="now"') < top.index(
        "FreeFlight WX"
    )  # in the page order the weather is first
    # on wide screens the weather panel is moved to the second column, so the station is on the left
    assert (
        "@media (min-width:44rem){.top{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}"
        ".top>#now{order:2}}" in html
    )
    assert "minmax(0,1fr)}" in html  # stacks to one column on phones, in page order


def test_chart_is_requested_at_half_width(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "width=440&amp;height=380" in html or "width=440&height=380" in html
    assert 'width="440"' in html and "max-width:440px" in html
    assert "width=780" not in html


def test_today_forecast_table_is_filled_from_hourly_data(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert 'id="today-rows-mystic"' in html and "Forecast for the rest of today" in html
    assert "&hourly=temperature_2m,precipitation_probability" in html
    assert "forecast_days=1" in html
    for col in ("Time", "Temp", "Rain", "Wind (gusts)"):
        assert f"<th>{col}</th>" in html


def test_only_our_two_small_scripts(fixture_path, site, rules):
    assert re.findall(r"<script[^>]*>", page(fixture_path, site, rules)) == [
        '<script id="prefs">',
        '<script id="enhance">',
    ]


def test_launch_wind_in_every_collapsed_header(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    rows = re.findall(r'<details class="day"[^>]*>.*?</details>', html, flags=re.S)
    for row in rows:
        summary = re.search(r"<summary>(.*?)</summary>", row, flags=re.S)
        assert summary is not None
        assert summary.group(1).count('class="clw"') == 9  # one per hourly column
        assert summary.group(1).count('class="dir ') == 9  # one coloured arrow per column
        assert "transform:rotate(" in summary.group(1)
        assert "Wind at launch" in row and "800 m" in row  # and a labelled row in the details
    assert "800 m" in html and "2,625 ft" in html  # launch altitude, in both height units


def test_old_forecasts_without_launch_wind_still_render(site, rules, fixture_path):
    import json as _json

    d = _json.loads(fixture_path.read_text())
    for b in d["blocks"]:
        b.pop("wind_launch", None)
    html = render_page(Forecast.from_dict(d), site, rules)
    rows = re.findall(r'<details class="day"[^>]*>.*?</summary>', html, flags=re.S)
    assert rows and all('class="clw"' not in r for r in rows)  # no launch wind in the day headers
    assert "<summary>" in html
