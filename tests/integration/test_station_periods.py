import html as htmllib
import json
import re

import pytest

from ffforecast.config import ConfigError, load_site
from ffforecast.models import Forecast
from ffforecast.render import render_page

PERIODS = [
    ("cur", "Current", "current"),
    ("1h", "1 hr", "last hour"),
    ("4h", "4 hr", "last 4 hours"),
    ("12h", "12 hr", "last 12 hours"),
    ("day", "Day", "today"),
]


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def panel(html):
    a = html.index('<section aria-label="Weather station">')
    return html[a : html.index("</section>", a)]


def test_toggle_has_current_1_4_12_and_day_with_4_hours_chosen_first(fixture_path, site, rules):
    p = panel(page(fixture_path, site, rules))
    labels = re.findall(r'<label for="st-([a-z0-9]+)">([^<]+)</label>', p)
    assert labels == [(i, label) for i, label, _ in PERIODS]
    assert '<input type="radio" name="st" id="st-4h" checked>' in p
    assert p.count(" checked") == 1  # exactly one period chosen
    assert '<legend class="sr">Chart period</legend>' in p


def test_the_heading_is_only_the_stations_name_as_a_link(fixture_path, site, rules):
    p = panel(page(fixture_path, site, rules))
    h2 = re.search(r"<h2>(.*?)</h2>", p, flags=re.S)
    assert h2 is not None
    assert (
        h2.group(1) == '<a href="https://www.freeflightwx.com/mystic/index.php">FreeFlight WX</a>'
    )
    assert "last 4 hours" not in h2.group(1)  # the period is the chosen button, not in the heading


def test_each_period_has_its_own_chart_and_full_page_link(fixture_path, site, rules):
    p = panel(page(fixture_path, site, rules))
    pages = {
        "cur": "index.php",
        "1h": "1hour.php",
        "4h": "4hours.php",
        "12h": "12hours.php",
        "day": "day.php",
    }
    for pid, page_name in pages.items():
        assert f'<a class="st st-{pid}"' not in p  # the separate text links were dropped
        expected = f"https://www.freeflightwx.com/mystic/{page_name}"
        wrap = re.search(
            rf'<p class="st st-{pid}"><a href="([^"]+)"[^>]*><img class="history" data-src="([^"]+)"',
            p,
        )
        assert wrap is not None and wrap.group(1) == expected  # the chart itself links to its page
        assert "width=440&height=380" in htmllib.unescape(wrap.group(2))
    plain = htmllib.unescape(p)
    assert (
        "time=600&" in plain
        and "time=3600&" in plain
        and "time=14400&" in plain
        and "time=43200&" in plain
    )
    assert "windgraph2.php?begin=today&end=tomorrow" in plain  # the day chart is a different script


def test_links_open_a_new_page_safely(fixture_path, site, rules):
    p = panel(page(fixture_path, site, rules))
    anchors = re.findall(r"<a [^>]*>", p)
    heading, rest = anchors[0], anchors[1:]
    # the heading link (the owner's change) goes to the station page in the same tab; every other
    # link in the panel opens a new tab
    assert 'href="https://www.freeflightwx.com/mystic/index.php"' in heading
    assert 'target="_blank"' not in heading
    assert len(rest) == 5  # one link per period: the chart itself (the text links were dropped)
    for a in rest:
        assert (
            'target="_blank"' in a and 'rel="noopener noreferrer"' in a
        )  # new tab, no window.opener


def test_only_the_chosen_chart_is_shown_so_only_it_is_fetched(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert ".st{display:none}" in html
    for pid, _, _ in PERIODS:
        assert f"body:has(#st-{pid}:checked) p.st-{pid}{{display:block}}" in html
        assert (
            f"body:has(#st-{pid}:checked) span.st-{pid},body:has(#st-{pid}:checked) a.st-{pid}{{display:inline}}"
            in html
        )
    p = panel(html)
    # no chart is in the page until it is wanted: the script gives the chosen one its address, so
    # the others are never requested (checked in a real browser: lazy loading alone did not hold
    # hidden charts back)
    history = re.findall(r'<img class="history"[^>]*>', p)
    assert len(history) == 5 and all(" src=" not in i and "data-src=" in i for i in history)
    assert 'loading="lazy"' not in re.sub(
        r"<iframe.*?</iframe>", "", p, flags=re.S
    )  # the charts; the gauge frame is lazy


def test_chart_refreshes_for_the_visible_period_only(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "function freshen()" in html and "im.offsetParent!==null" in html
    assert (
        'document.querySelectorAll("input[name=st]")' in html
        and 'addEventListener("change",freshen)' in html
    )
    assert 'id="history"' not in html  # one element per period now, so it is a class


def test_period_is_remembered_with_the_other_settings(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    # the radios sit below the settings script, so it re-applies and re-binds once the page has loaded
    assert 'document.addEventListener("DOMContentLoaded",applyAll);' in html
    assert "if(!inputs[i].__ff)" in html  # never bound twice
    assert 'id="st-12h"' in html


def test_period_choice_looks_like_the_other_toggles(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert ".periods input:checked+label{" in html and ".periods input:focus-visible+label{" in html


# ---- configuration -----------------------------------------------------------------------------


def write_site(tmp_path, extra=""):
    text = open("config/site.mystic.toml").read() + extra
    p = tmp_path / "site.toml"
    p.write_text(text)
    return p


def test_real_config_has_the_five_periods(site):
    assert [c["id"] for c in site.station_charts] == [p[0] for p in PERIODS]
    assert site.station_default == "4h"


def test_default_must_be_one_of_the_periods(tmp_path):
    text = (
        open("config/site.mystic.toml")
        .read()
        .replace('station_default = "4h"', 'station_default = "9h"')
    )
    p = tmp_path / "s.toml"
    p.write_text(text)
    with pytest.raises(ConfigError, match="station_default"):
        load_site(p)


def test_period_links_must_be_https_and_complete(tmp_path):
    text = (
        open("config/site.mystic.toml")
        .read()
        .replace(
            'page = "https://www.freeflightwx.com/mystic/1hour.php"', 'page = "http://x/1hour.php"'
        )
    )
    p = tmp_path / "s.toml"
    p.write_text(text)
    with pytest.raises(ConfigError, match="https"):
        load_site(p)
    p.write_text(open("config/site.mystic.toml").read().replace('link = "Full day page"\n', ""))
    with pytest.raises(ConfigError, match="link"):
        load_site(p)


def test_duplicate_period_ids_rejected(tmp_path):
    p = write_site(
        tmp_path,
        '\n[[station_charts]]\nid = "4h"\nlabel = "x"\nheading = "x"\nlink = "x"\npage = "https://a"\nchart = "https://b"\n',
    )
    with pytest.raises(ConfigError, match="unique"):
        load_site(p)


def test_default_chart_still_loads_without_scripts(fixture_path, site, rules):
    p = panel(page(fixture_path, site, rules))
    nos = re.findall(r"<noscript>(.*?)</noscript>", p, flags=re.S)
    assert len(nos) == 1  # only the default period
    assert "time=14400" in htmllib.unescape(nos[0]) and "<img src=" in nos[0]


def test_chosen_chart_is_loaded_by_the_script_at_start(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "freshen(); // load the chosen period now" in html
    assert 'im.src=base+(base.indexOf("?")>-1?"&":"?")+"rand="+Date.now()' in html


def test_saved_period_is_applied_before_the_chart_is_chosen(fixture_path, site, rules):
    # the period radios sit below the settings script; the chart loader must see the saved choice
    # (this was a real bug: the saved 12 hr period was ticked but the default 4 hr chart was loaded)
    html = page(fixture_path, site, rules)
    assert "window.ffApplyPrefs=applyAll;" in html
    assert html.index("window.ffApplyPrefs();") < html.index(
        "freshen(); // load the chosen period now"
    )
