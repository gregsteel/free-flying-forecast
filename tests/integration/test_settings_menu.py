import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def test_hamburger_button_opens_a_settings_menu(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    m = re.search(
        r'<details class="menu" id="menu">\s*<summary([^>]*)>(.*?)</summary>', html, flags=re.S
    )
    assert m is not None
    assert 'aria-label="Settings"' in m.group(1)  # an icon button needs a text name
    assert m.group(2).count("<path") == 1 and "M3 6h18M3 12h18M3 18h18" in m.group(2)  # three bars
    assert "<details" in html and 'class="menu"' in html


def test_menu_is_closed_by_default_and_works_without_javascript(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert '<details class="menu" id="menu">' in html  # no "open" attribute
    # the toggle is the native details element; the script only adds outside-click and Escape
    assert "menu.open=false" in html and 'e.key==="Escape"' in html


def test_all_unit_choices_live_inside_the_menu(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    menu = html[
        html.index('<details class="menu"') : html.index(
            "</details>", html.index('<details class="menu"')
        )
    ]
    for ident in ("sp-kts", "sp-kph", "al-m", "al-ft", "tp-c", "tp-f"):
        assert f'id="{ident}"' in menu
    assert "saved in a cookie in this browser" in menu and "holds only these settings" in menu
    # and nowhere else: the page has no second, stray copy of the selector
    assert html.count('type="radio"') == 15  # glider 2, units 6, station period 5, weather place 2


def test_hamburger_sits_in_the_page_header_beside_the_title(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    bar = html[html.index('<header class="bar">') : html.index("</header>")]
    assert bar.index("<h1>") < bar.index('<details class="menu"')  # title first, menu at the right
    assert "justify-content:space-between" in html


def test_units_still_switch_with_the_menu_closed(fixture_path, site, rules):
    # the CSS rules key off the radios wherever they are in the page, so a closed menu still works
    html = page(fixture_path, site, rules)
    assert "body:has(#sp-kph:checked)" in html and "body:has(#al-ft:checked)" in html


def test_menu_panel_has_a_heading_and_stays_on_screen(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "<h2>Settings</h2>" in html
    assert "width:min(19rem,calc(100vw - 2rem))" in html  # never wider than a phone
