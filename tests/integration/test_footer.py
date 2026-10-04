import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def test_footer_has_sources_and_credits(fixture_path, site, rules):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    html = render_page(fc, site, rules)
    footer = html[html.index("<footer>") :]
    assert "Advisory only" in footer
    assert "Rules version" not in html  # the version number is kept in forecast.json only
    assert (
        "Generated " not in footer and "Cycle " not in footer
    )  # the run details are in the header
    assert "NOAA GFS" in footer
    assert "FreeFlightWx" in footer and "NEVHGC" in footer
    # the station page, FreeFlightWx itself and the club; the period pages and the gauge are linked
    # in the weather station panel instead
    for url in (
        "https://www.freeflightwx.com/mystic/index.php",
        "https://www.freeflightwx.com/",
        "https://www.nevhgc.net",
    ):
        assert f'href="{url}"' in footer
    assert (
        "wind speed and wind direction rules are based on the published Mystic site settings"
        in footer
    )
    assert 'href="https://open-meteo.com/"' in footer and "CC BY 4.0" in footer


def test_footer_names_the_panel_by_its_current_name(fixture_path, site, rules):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    html = render_page(fc, site, rules)
    footer = html[html.index("<footer>") :]
    assert 'The "Today at Mystic" panel' in footer and "Open-Meteo.com" in footer
    # "Right now" was the panel's first name; nothing on the page should still use it
    assert "right now" not in html.lower()


def test_footer_acknowledges_ausrasp_and_its_victorian_supporter(fixture_path, site, rules):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    footer = (lambda h: h[h.index("<footer>") :])(render_page(fc, site, rules))
    assert "calibrated against" in footer and ">AUSRASP</a> forecasts" in footer
    for url in ("https://www.ausrasp.com/", "https://ausrasp.com/VIC/", "https://www.vhpa.org.au/"):
        assert f'href="{url}"' in footer
    assert ">Victoria forecast</a> is supported by the" in footer
    assert "Victorian Hang Gliding and Paragliding Association (VHPA)" in footer
    assert "run on" in footer and "donations" in footer
    assert "muppet" not in footer.lower()


def test_the_acknowledgement_links_come_from_the_site_config(site):
    assert site.links["vhpa"].startswith("https://") and "ausrasp" in site.links["ausrasp_vic"]


def test_the_header_carries_the_model_run_and_update_time_in_one_line(fixture_path, site, rules):
    import re

    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    html = render_page(fc, site, rules)
    m = re.search(r'<p class="muted">(Updated .*?)</p>', html)
    assert m is not None
    line = m.group(1)
    assert line.startswith("Updated Sat 03 Oct 2026 13:00 AEST. Model: NOAA GFS")
    assert ", run 2026-10-03T00Z." in line and "Thermals:" in line
    assert html.index(line) < html.index('<div class="top">')  # in the pinned header


def test_the_rules_source_line_is_not_shown_on_the_page(fixture_path, site, rules):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    html = render_page(fc, site, rules)
    assert "Rules source" not in html and rules.source not in html  # it stays in rules.toml only


def test_the_header_ends_with_the_own_use_statement(fixture_path, site, rules):
    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    html = render_page(fc, site, rules)
    pinned = html[html.index('<div class="sticky" id="sticky">') : html.index('<div class="top">')]
    statement = (
        "This page was made for my own use, you are welcome to use it (but don't complain). "
        "Or fork the project and make your own."
    )
    plain = re.sub(r"<[^>]+>", "", pinned)
    assert statement in re.sub(r"\s+", " ", plain)
    assert pinned.rindex("This page was made for my own use") > pinned.rindex('id="stale"')  # last


def test_the_fork_the_project_words_link_to_github_once_it_is_configured(fixture_path, site, rules):
    import dataclasses

    fc = Forecast.from_dict(json.loads(fixture_path.read_text()))
    norepo = dataclasses.replace(site, links={k: v for k, v in site.links.items() if k != "github"})
    assert "fork the project</a>" not in render_page(fc, norepo, rules)  # no repository set
    withrepo = dataclasses.replace(
        site, links={**site.links, "github": "https://github.com/example/free-flying-forecast"}
    )
    html = render_page(fc, withrepo, rules)
    assert (
        '<a href="https://github.com/example/free-flying-forecast" target="_blank" '
        'rel="noopener noreferrer">fork the project</a>' in html
    )
