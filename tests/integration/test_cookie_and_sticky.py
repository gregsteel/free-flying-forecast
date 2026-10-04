import json
import re

from ffforecast.models import Forecast
from ffforecast.render import render_page


def page(fixture_path, site, rules):
    return render_page(Forecast.from_dict(json.loads(fixture_path.read_text())), site, rules)


def prefs_script(html: str) -> str:
    m = re.search(r'<script id="prefs">(.*?)</script>', html, flags=re.S)
    assert m is not None
    return m.group(1)


# ---- settings are kept in a cookie ------------------------------------------------------------


def test_settings_are_stored_in_a_first_party_cookie(fixture_path, site, rules):
    js = prefs_script(page(fixture_path, site, rules))
    assert 'NAME="ffforecast-prefs"' in js and "document.cookie=" in js
    assert "Max-Age=" in js and "SameSite=Lax" in js
    assert 'location.protocol==="https:"?"; Secure"' in js  # Secure whenever the site is https
    assert "HttpOnly" not in js  # script-set cookies cannot be; the cookie holds only choices


def test_cookie_is_scoped_to_this_sites_folder_not_the_whole_host(fixture_path, site, rules):
    js = prefs_script(page(fixture_path, site, rules))
    assert 'function dir(){return location.pathname.replace(/[^\\/]*$/,"")||"/";}' in js
    assert '"; Path="+dir()' in js  # so other sites on a shared host never see it


def test_cookie_value_cannot_inject_anything(fixture_path, site, rules):
    js = prefs_script(page(fixture_path, site, rules))
    # a cookie is user-controlled input: only ever tick an existing radio that belongs to that setting
    assert 'el&&el.type==="radio"&&el.name===k' in js
    assert "hasOwnProperty" in js and "innerHTML" not in js and "eval(" not in js


def test_local_storage_is_only_a_fallback_and_everything_is_guarded(fixture_path, site, rules):
    js = prefs_script(page(fixture_path, site, rules))
    assert "fromCookie()" in js and "fromStorage()" in js
    assert js.index("fromCookie()") < js.index("if(!o){try{o=fromStorage()")  # cookie first
    assert js.count("catch(x){}") >= 4  # blocked cookies or storage never break the page


def test_menu_tells_people_about_the_cookie(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "saved in a cookie in this browser" in html and "holds only these settings" in html


def test_saved_settings_apply_before_the_page_is_drawn(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    # the settings script sits straight after the controls and before any forecast content,
    # so a returning visitor never sees a flash of the defaults
    assert html.index('<script id="prefs">') < html.index('<div class="top">')
    assert html.index('<script id="prefs">') < html.index("<h2>Next ")
    assert html.index('id="gl-hg"') < html.index('<script id="prefs">')  # after the radios exist


def test_every_setting_is_covered_by_the_cookie(fixture_path, site, rules):
    js = prefs_script(page(fixture_path, site, rules))
    assert 'document.querySelectorAll("input[type=radio]")' in js  # glider and all three units


# ---- pinned header ------------------------------------------------------------------------------


def test_title_settings_update_time_and_alert_are_pinned(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    start = html.index('<div class="sticky" id="sticky">')
    end = html.index('<div class="top">')
    pinned = html[start:end]
    for part in (
        "<h1>",
        'class="glider"',
        '<details class="menu"',
        "Updated ",
        'role="alert"',
        'id="stale"',
    ):
        assert part in pinned
    assert "Next 4 days" not in pinned and 'id="now"' not in pinned  # the content scrolls
    assert "position:sticky;top:0" in html and "z-index:30" in html


def test_pinned_header_has_a_background_and_stays_compact(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert ".sticky{position:sticky;top:0;z-index:30;background:var(--bg)" in html
    assert ".sticky .banner{margin:.4rem 0 0;padding:.35rem .6rem;font-size:.9rem}" in html
    assert "@media (max-width:44rem){.sticky h1{font-size:1.05rem;line-height:1.2}}" in html


def test_scrolled_to_content_stops_below_the_pinned_header(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert "html{scroll-padding-top:calc(var(--hdr,6rem) + .75rem)}" in html  # works without JS
    assert 'document.documentElement.style.setProperty("--hdr",st.offsetHeight+"px")' in html
    assert "new ResizeObserver(setHdr)" in html  # follows the alert appearing or wrapping


def test_settings_menu_still_opens_above_the_content(fixture_path, site, rules):
    html = page(fixture_path, site, rules)
    assert ".panel{position:absolute;right:0;top:3.3rem;z-index:20" in html
    assert html.index('<div class="sticky"') < html.index(
        '<details class="menu"'
    )  # menu is inside it
