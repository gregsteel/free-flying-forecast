import json
import re

from ffforecast.models import Forecast
from ffforecast.render import alt, rate, render_page, spd, temp, unitise


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def test_defaults_are_knots_metres_celsius(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert 'id="sp-kts" checked' in html
    assert 'id="al-m" checked' in html
    assert 'id="tp-c" checked' in html
    # default-visible classes
    assert ".s-kts,.a-m,.t-c{display:inline}" in html


def test_every_unit_has_a_selector_and_css_rule(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    for ident in ("sp-kts", "sp-kph", "al-m", "al-ft", "tp-c", "tp-f"):
        assert f'id="{ident}"' in html
    for ident in ("sp-kph", "al-ft", "tp-f"):
        assert f"body:has(#{ident}:checked)" in html


def test_selector_works_without_javascript(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    # the selector is plain radio inputs plus CSS; the script only remembers the choice
    assert html.count('type="radio"') == 15
    assert "localStorage" in html and "try{" in html


def test_wind_is_only_knots_and_kmh(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert 'id="sp-mph"' not in html and 'id="sp-ms"' not in html
    assert "s-mph" not in html and "s-ms" not in html
    assert ">mph<" not in html and ">m/s<" not in html.split("<style>")[0].replace(
        "m/s updraft", ""
    )


def test_all_values_present_in_all_units():
    assert [m.group(1) for m in re.finditer(r">([^<]+)</span>", spd(18.52))] == ["10 kts", "19 kph"]
    assert "1,000 m" in alt(1000) and "3,281 ft" in alt(1000)
    assert "2.0 m/s" in rate(2.0) and "6.6 ft/sec" in rate(2.0)
    assert "0 \u00b0C" in temp(0) and "32 \u00b0F" in temp(0)


def test_reason_text_follows_selected_units():
    out = str(unitise("Wind 20 kph is above 19 kph: may not suit novice pilots. (885 m)"))
    assert out.count("s-kts") == 2 and out.count("s-kph") == 2 and out.count("a-ft") == 1
    assert "may not suit novice pilots" in out


def test_reason_text_is_escaped():
    assert "&lt;script&gt;" in str(unitise("<script> 5 kph"))


def test_updraft_in_feet_is_ft_per_second_to_one_decimal():
    from ffforecast.render import rate, rate_whole

    for fn in (rate, rate_whole):
        out = str(fn(2.0))
        assert '<span class="u a-ft">6.6 ft/sec</span>' in out  # 6.56 ft/s
        assert "ft/min" not in out
    assert '<span class="u a-ft">0.3 ft/sec</span>' in str(rate(0.1))
    assert '<span class="u a-ft">13.1 ft/sec</span>' in str(rate(4.0))
