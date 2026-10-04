import json

from ffforecast.models import Forecast
from ffforecast.render import render_page, unitise


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def test_wet_days_banner_links_to_bom(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert 'role="alert"' in html and "Rain or storms are possible on" in html
    assert html.count('href="https://www.bom.gov.au/vic/warnings/"') >= 2  # banner and footer


def test_blocks_show_rain_gusts_and_reasons(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "<dt>Rain</dt>" in html and "<dt>Gusts</dt>" in html
    assert "Heavy rain expected" in html and "Thunderstorm risk" in html
    assert "mm/h" in html and "in/h" in html  # follows the height unit selector


def test_outlook_flags_wet_days(fixture_path, site, rules):
    assert '<span class="cwet">Rain or storms possible</span>' in page(fixture_path, site, rules)


def test_dry_forecast_has_no_banner(site, rules):
    fc = Forecast("mystic", "m", "c", "2026-10-03T14:00:00+11:00", 1, [], [])
    assert 'role="alert"' not in render_page(fc, site, rules)


def test_rain_in_reasons_converts_units():
    out = str(unitise("Heavy rain expected (2.3 mm/h)."))
    assert "2.3 mm/h" in out and "0.09 in/h" in out
